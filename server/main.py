from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from typing import Optional, List
import uvicorn
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import atexit
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func, or_
import re
from dateutil import parser

from database import engine, SessionLocal, get_db
from models import Base, Job, Search, ScheduledSearch
from adzuna_client import AdzunaClient

# Load environment variables
load_dotenv()

# Create tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Job Hunting Bot API",
    description="Automated job search API using Adzuna",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Adzuna client
adzuna_client = AdzunaClient(
    api_key=os.getenv("ADZUNA_API_KEY"),
    app_id=os.getenv("ADZUNA_APP_ID")
)

# Initialize scheduler
scheduler = AsyncIOScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# Pydantic models
class ScheduleSearchRequest(BaseModel):
    keywords: str
    location: Optional[str] = None
    frequency: str = "daily"
    date_filter_days: Optional[int] = None

class SearchRequest(BaseModel):
    keywords: str
    location: Optional[str] = None
    date_filter_days: Optional[int] = None
    schedule: bool = False
    frequency: Optional[str] = "daily"

# Global variable to track latest automated search
latest_automated_search_id = None
def format_job_for_ui(job_data, source="api"):
    """
    Ensure consistent job formatting for UI display.
    Handles both database job objects and API job dictionaries.
    """
    if hasattr(job_data, 'external_id'):
        # Database job object
        return {
            "id": job_data.external_id,
            "title": job_data.title,
            "company": job_data.company,
            "location": job_data.location,
            "description": job_data.description,
            "apply_link": job_data.apply_link,
            "date_posted": job_data.date_posted,
            "salary_range": job_data.salary_range,
            "source": "database"
        }
    else:
        # API job dictionary - ensure consistent structure
        company_name = job_data.get("company", "")
        if isinstance(company_name, dict):
            company_name = company_name.get("display_name", "Company not specified")
        
        location_name = job_data.get("location", "")
        if isinstance(location_name, dict):
            location_name = location_name.get("display_name", "Location not specified")
        
        # Handle salary formatting consistently
        salary_range = None
        if job_data.get("salary_min") and job_data.get("salary_max"):
            salary_range = f"${job_data.get('salary_min'):,} - ${job_data.get('salary_max'):,}"
        elif job_data.get("salary_min"):
            salary_range = f"${job_data.get('salary_min'):,}+"
        
        return {
            "id": str(job_data.get("id", "")),
            "title": job_data.get("title", ""),
            "company": company_name,
            "location": location_name,
            "description": job_data.get("description", ""),
            "apply_link": job_data.get("redirect_url", ""),
            "date_posted": job_data.get("created", ""),
            "salary_range": salary_range,
            "source": source
        }


# Enhanced search functions
def normalize_search_terms(text):
    """
    Normalize search terms for better matching
    """
    if not text:
        return ""
    
    # Convert to lowercase and remove extra spaces
    text = re.sub(r'\s+', ' ', text.lower().strip())
    
    # Handle common job title variations
    variations = {
        'software engineer': ['software engineer', 'software developer', 'developer', 'programmer', 'swe'],
        'data scientist': ['data scientist', 'data analyst', 'machine learning engineer', 'ml engineer'],
        'product manager': ['product manager', 'pm', 'product owner', 'product lead'],
        'frontend': ['frontend', 'front-end', 'front end', 'ui developer', 'react developer'],
        'backend': ['backend', 'back-end', 'back end', 'server developer', 'api developer'],
        'fullstack': ['fullstack', 'full-stack', 'full stack'],
        'devops': ['devops', 'dev ops', 'site reliability engineer', 'sre', 'infrastructure engineer'],
        'qa': ['qa', 'quality assurance', 'test engineer', 'software tester']
    }
    
    # Find matching variations
    for key, terms in variations.items():
        if any(term in text for term in terms):
            return key
    
    return text

def get_existing_jobs_from_db(keywords, location, date_filter_days, db):
    """
    Get existing jobs from database that match the search criteria
    """
    normalized_keywords = normalize_search_terms(keywords)
    
    # Base query
    query = db.query(Job).join(Search)
    
    # Add keyword filtering - check both original keywords and normalized
    keyword_conditions = []
    
    # Split keywords into individual terms
    keyword_terms = normalized_keywords.split()
    for term in keyword_terms:
        keyword_conditions.extend([
            Job.title.ilike(f'%{term}%'),
            Job.description.ilike(f'%{term}%'),
            Job.company.ilike(f'%{term}%'),
            Search.keywords.ilike(f'%{term}%')
        ])
    
    # Also check original keywords
    original_terms = keywords.lower().split()
    for term in original_terms:
        keyword_conditions.extend([
            Job.title.ilike(f'%{term}%'),
            Job.description.ilike(f'%{term}%'),
            Job.company.ilike(f'%{term}%'),
            Search.keywords.ilike(f'%{term}%')
        ])
    
    query = query.filter(or_(*keyword_conditions))
    
    # Add location filtering if specified
    if location:
        location_terms = location.lower().split()
        location_conditions = []
        for term in location_terms:
            location_conditions.extend([
                Job.location.ilike(f'%{term}%'),
                Search.location.ilike(f'%{term}%')
            ])
        query = query.filter(or_(*location_conditions))
    
    # Add date filtering
    if date_filter_days:
        cutoff_date = datetime.utcnow() - timedelta(days=date_filter_days)
        
        # Filter by when we stored the job (more reliable than parsing job_posted dates)
        query = query.filter(Job.created_at >= cutoff_date)
    
    # Order by most recent first and remove duplicates
    existing_jobs = query.order_by(Job.created_at.desc()).all()
    
    # Remove duplicates based on external_id, title, and company
    seen = set()
    unique_jobs = []
    for job in existing_jobs:
        identifier = (job.external_id, job.title.lower(), job.company.lower())
        if identifier not in seen:
            seen.add(identifier)
            unique_jobs.append(job)
    
    return unique_jobs

def format_job_from_db(job):
    """
    Format database job record to match API response format
    """
    return {
        "id": job.external_id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": job.description,
        "apply_link": job.apply_link,
        "date_posted": job.date_posted,
        "salary_range": job.salary_range,
        "source": "database"
    }

def combine_db_and_api_jobs(db_jobs, api_jobs):
    """
    Combine database jobs with API jobs, removing duplicates
    """
    # Create a set of identifiers from database jobs
    db_identifiers = set()
    for job in db_jobs:
        if isinstance(job, dict):
            identifier = (str(job.get("id", "")), job.get("title", "").lower(), job.get("company", "").lower())
        else:
            identifier = (str(job.external_id), job.title.lower(), job.company.lower())
        db_identifiers.add(identifier)
    
    # Filter API jobs to exclude those already in database
    new_api_jobs = []
    for job in api_jobs:
        api_identifier = (
            str(job.get("id", "")), 
            job.get("title", "").lower(), 
            job.get("company", {}).get("display_name", "").lower()
        )
        
        if api_identifier not in db_identifiers:
            job["source"] = "api"
            new_api_jobs.append(job)
    
    # Format database jobs if needed
    formatted_db_jobs = []
    for job in db_jobs:
        if isinstance(job, dict):
            formatted_db_jobs.append(job)
        else:
            formatted_db_jobs.append(format_job_from_db(job))
    
    # Combine and sort by date (most recent first)
    all_jobs = formatted_db_jobs + new_api_jobs
    
    # Sort by date posted (handle various date formats)
    def get_job_date(job):
        date_str = job.get("date_posted", "")
        if not date_str:
            return datetime.min
        
        try:
            if date_str.endswith('Z'):
                return datetime.fromisoformat(date_str.replace('Z', '+00:00')).replace(tzinfo=None)
            else:
                return datetime.fromisoformat(date_str)
        except:
            return datetime.min
    
    all_jobs.sort(key=get_job_date, reverse=True)
    
    return all_jobs, len(new_api_jobs), len(formatted_db_jobs)

def filter_jobs_by_date(jobs_list: List[dict], days_filter: Optional[int]) -> List[dict]:
    """
    Filter jobs by date posted. Returns only jobs within the specified number of days.
    If days_filter is None, returns all jobs.
    """
    if not days_filter:
        return jobs_list
    
    cutoff_date = datetime.utcnow() - timedelta(days=days_filter)
    filtered_jobs = []
    
    for job in jobs_list:
        job_date_str = job.get("created")
        if not job_date_str:
            # If no date, include job (assume recent)
            filtered_jobs.append(job)
            continue
            
        try:
            # Parse the job date (Adzuna format: "2024-08-27T14:30:00Z")
            if job_date_str.endswith('Z'):
                job_date = datetime.fromisoformat(job_date_str.replace('Z', '+00:00'))
            else:
                job_date = datetime.fromisoformat(job_date_str)
            
            # Convert to UTC if timezone aware
            if job_date.tzinfo:
                job_date = job_date.replace(tzinfo=None)
            
            # Include job if it's within the date range
            if job_date >= cutoff_date:
                filtered_jobs.append(job)
                
        except (ValueError, TypeError) as e:
            # If date parsing fails, include the job
            print(f"Failed to parse job date '{job_date_str}': {e}")
            filtered_jobs.append(job)
    
    return filtered_jobs

# Serve static files
if os.path.exists("../client/dist"):
    app.mount("/static", StaticFiles(directory="../client/dist"), name="static")

@app.on_event("startup")
async def startup_event():
    await load_existing_scheduled_searches()

async def load_existing_scheduled_searches():
    db = SessionLocal()
    try:
        active_schedules = db.query(ScheduledSearch).filter(ScheduledSearch.is_active == "true").all()
        for schedule in active_schedules:
            try:
                await add_scheduler_job(schedule)
                print(f"Restored scheduled search: {schedule.keywords} ({schedule.frequency})")
            except Exception as e:
                print(f"Failed to restore scheduled search {schedule.id}: {e}")
    except Exception as e:
        print(f"Error loading scheduled searches: {e}")
    finally:
        db.close()

async def add_scheduler_job(scheduled_search: ScheduledSearch):
    job_id = f"scheduled_search_{scheduled_search.id}"
    
    try:
        scheduler.remove_job(job_id)
    except:
        pass
    
    # Define trigger based on frequency
    trigger_map = {
        "1min": IntervalTrigger(minutes=1),
        "hourly": IntervalTrigger(hours=1),
        "2hours": IntervalTrigger(hours=2),
        "3hours": IntervalTrigger(hours=3),
        "6hours": IntervalTrigger(hours=6),
        "daily": IntervalTrigger(days=1),
        "weekly": IntervalTrigger(weeks=1)
    }
    trigger = trigger_map.get(scheduled_search.frequency, IntervalTrigger(hours=1))
    
    scheduler.add_job(
        run_scheduled_search,
        trigger=trigger,
        args=[scheduled_search.id],
        id=job_id,
        name=f"Search: {scheduled_search.keywords}",
        replace_existing=True
    )
    
    # Update next_run time
    db = SessionLocal()
    try:
        schedule = db.query(ScheduledSearch).filter(ScheduledSearch.id == scheduled_search.id).first()
        if schedule:
            time_deltas = {
                "1min": timedelta(minutes=1),
                "hourly": timedelta(hours=1),
                "2hours": timedelta(hours=2),
                "3hours": timedelta(hours=3),
                "6hours": timedelta(hours=6),
                "daily": timedelta(days=1),
                "weekly": timedelta(weeks=1)
            }
            schedule.next_run = datetime.utcnow() + time_deltas.get(scheduled_search.frequency, timedelta(hours=1))
            db.commit()
    finally:
        db.close()

async def run_scheduled_search(scheduled_search_id: int):
    global latest_automated_search_id
    db = SessionLocal()
    try:
        scheduled_search = db.query(ScheduledSearch).filter(ScheduledSearch.id == scheduled_search_id).first()
        if not scheduled_search or scheduled_search.is_active != "true":
            return
        
        print(f"Running enhanced scheduled search: {scheduled_search.keywords}")
        
        # Step 1: Get existing jobs from database (SAME AS MANUAL SEARCH)
        existing_jobs = get_existing_jobs_from_db(
            scheduled_search.keywords,
            scheduled_search.location,
            scheduled_search.date_filter_days,
            db
        )
        print(f"Found {len(existing_jobs)} existing jobs in database for scheduled search")
        
        # Step 2: Get fresh jobs from API (SAME AS MANUAL SEARCH)
        all_api_jobs = []
        page = 1
        max_pages = 5  # Limit pages for scheduled searches to prevent long runtime
        
        while page <= max_pages:
            search_params = {
                "keywords": scheduled_search.keywords,
                "location": scheduled_search.location,
                "results_per_page": 50,
                "page": page
            }
            
            jobs_data = await adzuna_client.search_jobs(**search_params)
            page_jobs = jobs_data.get("jobs", [])
            
            if not page_jobs:
                break
            
            all_api_jobs.extend(page_jobs)
            
            if len(page_jobs) < 50:
                break
                
            page += 1
        
        print(f"Retrieved {len(all_api_jobs)} jobs from API for scheduled search")
        
        # Step 3: Apply date filter to API jobs (SAME AS MANUAL SEARCH)
        if scheduled_search.date_filter_days:
            filtered_api_jobs = filter_jobs_by_date(all_api_jobs, scheduled_search.date_filter_days)
        else:
            filtered_api_jobs = all_api_jobs
        
        print(f"After date filtering: {len(filtered_api_jobs)} API jobs for scheduled search")
        
        # Step 4: Combine database jobs with new API jobs (SAME AS MANUAL SEARCH)
        combined_jobs, new_api_count, db_count = combine_db_and_api_jobs(
            existing_jobs, 
            filtered_api_jobs
        )
        
        print(f"Combined results for scheduled search: {len(combined_jobs)} total jobs ({db_count} from DB, {new_api_count} new from API)")
        
        # Step 5: Store new API jobs and create search record (SAME AS MANUAL SEARCH)
        search_record = Search(
            keywords=scheduled_search.keywords,
            location=scheduled_search.location or "",
            results_count=len(combined_jobs)
        )
        db.add(search_record)
        db.commit()
        db.refresh(search_record)
        
        # Set this as the latest automated search for UI polling
        latest_automated_search_id = search_record.id
        
        # Store only new jobs in database
        jobs_stored = 0
        for job_data in filtered_api_jobs:
            existing_job = db.query(Job).filter(
                and_(
                    Job.external_id == str(job_data.get("id", "")),
                    Job.title == job_data.get("title", ""),
                    Job.company == job_data.get("company", {}).get("display_name", "")
                )
            ).first()
            
            if not existing_job:
                salary_range = None
                if job_data.get("salary_min") and job_data.get("salary_max"):
                    salary_range = f"${job_data.get('salary_min'):,} - ${job_data.get('salary_max'):,}"
                elif job_data.get("salary_min"):
                    salary_range = f"${job_data.get('salary_min'):,}+"
                
                job = Job(
                    external_id=str(job_data.get("id", "")),
                    title=job_data.get("title", ""),
                    company=job_data.get("company", {}).get("display_name", ""),
                    location=job_data.get("location", {}).get("display_name", ""),
                    description=job_data.get("description", "")[:1000],
                    apply_link=job_data.get("redirect_url", ""),
                    date_posted=job_data.get("created", ""),
                    salary_range=salary_range,
                    search_id=search_record.id
                )
                db.add(job)
                jobs_stored += 1
        
        # Update last run time
        scheduled_search.last_run = datetime.utcnow()
        db.commit()
        
        print(f"Enhanced scheduled search completed: {len(combined_jobs)} total jobs ({db_count} from DB + {jobs_stored} new) for '{scheduled_search.keywords}'")
        
        # Return the results in the same format as manual search for UI polling
        return {
            "search_record": search_record,
            "combined_jobs": combined_jobs,
            "db_count": db_count,
            "new_api_count": new_api_count
        }
        
    except Exception as e:
        print(f"Enhanced scheduled search failed for ID {scheduled_search_id}: {e}")
        db.rollback()
        return None
    finally:
        db.close()

@app.get("/")
async def read_root():
    if os.path.exists("../client/dist/index.html"):
        return FileResponse("../client/dist/index.html")
    return {"message": "Job Hunting Bot API is running! Visit /docs for API documentation."}

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "Job Hunting Bot API is running",
        "adzuna_configured": bool(os.getenv("ADZUNA_API_KEY") and os.getenv("ADZUNA_APP_ID")),
        "scheduler_running": scheduler.running,
        "active_jobs": len(scheduler.get_jobs())
    }

@app.get("/api/latest-automated-search")
async def get_latest_automated_search():
    global latest_automated_search_id
    
    if not latest_automated_search_id:
        return {"search": None, "jobs": []}
    
    db = SessionLocal()
    try:
        search = db.query(Search).filter(Search.id == latest_automated_search_id).first()
        if not search:
            return {"search": None, "jobs": []}
        
        jobs = db.query(Job).filter(Job.search_id == latest_automated_search_id).all()
        
        formatted_jobs = []
        for job in jobs:
            formatted_jobs.append({
                "id": job.external_id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "description": job.description,
                "apply_link": job.apply_link,
                "date_posted": job.date_posted,
                "salary_range": job.salary_range,
                "source": "database"
            })
        
        return {
            "search": {
                "keywords": search.keywords,
                "location": search.location,
                "results_count": search.results_count,
                "created_at": search.created_at.isoformat()
            },
            "jobs": formatted_jobs
        }
        
    finally:
        db.close()

# Update the get_recent_automated_searches endpoint to use consistent formatting
@app.get("/api/recent-automated-searches")
async def get_recent_automated_searches(
    since: Optional[str] = Query(None, description="ISO timestamp to get searches since"),
    db: Session = Depends(get_db)
):
    """
    Get recent searches with their jobs since a given timestamp.
    This endpoint returns consistently formatted jobs for UI display.
    """
    try:
        # Parse the since parameter
        if since:
            try:
                since_datetime = parser.isoparse(since)
                if since_datetime.tzinfo:
                    since_datetime = since_datetime.replace(tzinfo=None)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid timestamp format")
        else:
            # Default to last 5 minutes if no timestamp provided
            since_datetime = datetime.utcnow() - timedelta(minutes=5)
        
        # Get searches created since the timestamp
        recent_searches = (
            db.query(Search)
            .filter(Search.created_at >= since_datetime)
            .order_by(Search.created_at.desc())
            .limit(10)
            .all()
        )
        
        search_results = []
        for search in recent_searches:
            # Get ALL jobs for this search from database
            db_jobs = db.query(Job).filter(Job.search_id == search.id).all()
            
            # Also get existing jobs that match this search criteria
            existing_matched_jobs = get_existing_jobs_from_db(
                search.keywords,
                search.location,
                None,  # Don't apply date filter here since we want all relevant jobs
                db
            )
            
            # Format all jobs consistently using the helper function
            all_formatted_jobs = []
            
            # Add database jobs from this specific search (these are the "new" API jobs)
            for job in db_jobs:
                formatted_job = format_job_for_ui(job, source="api")  # These were newly added from API
                all_formatted_jobs.append(formatted_job)
            
            # Add other matching jobs from database (avoid duplicates)
            for job in existing_matched_jobs:
                job_id = job.external_id if hasattr(job, 'external_id') else job.get('id')
                if not any(existing['id'] == job_id for existing in all_formatted_jobs):
                    formatted_job = format_job_for_ui(job, source="database")
                    all_formatted_jobs.append(formatted_job)
            
            # Add to results if there are jobs
            if all_formatted_jobs:
                search_results.append({
                    "search": {
                        "id": search.id,
                        "keywords": search.keywords,
                        "location": search.location,
                        "results_count": len(all_formatted_jobs),
                        "created_at": search.created_at.isoformat(),
                        "search_type": "automated"
                    },
                    "jobs": all_formatted_jobs
                })
        
        return {
            "searches": search_results,
            "count": len(search_results),
            "since": since_datetime.isoformat() if since_datetime else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recent automated searches: {str(e)}")
    
# Also update the unified search endpoint to use consistent formatting
@app.post("/api/search")
async def unified_search(request: SearchRequest, db: Session = Depends(get_db)):
    """Enhanced unified search that combines database and API results with consistent formatting"""
    try:
        if not adzuna_client.api_key or not adzuna_client.app_id:
            raise HTTPException(
                status_code=500,
                detail="Adzuna API credentials not configured."
            )
        
        if request.schedule:
            # Handle scheduled search creation (no changes needed here)
            valid_frequencies = ["1min", "hourly", "2hours", "3hours", "6hours", "daily", "weekly"]
            if request.frequency not in valid_frequencies:
                raise HTTPException(status_code=400, detail=f"Invalid frequency. Must be one of: {valid_frequencies}")
            
            scheduled_search = ScheduledSearch(
                keywords=request.keywords,
                location=request.location or "",
                frequency=request.frequency,
                is_active="true",
                date_filter_days=request.date_filter_days,
                created_at=datetime.utcnow()
            )
            
            db.add(scheduled_search)
            db.commit()
            db.refresh(scheduled_search)
            
            await add_scheduler_job(scheduled_search)
            
            return {
                "message": "Scheduled search created successfully",
                "schedule_id": scheduled_search.id,
                "keywords": scheduled_search.keywords,
                "location": scheduled_search.location,
                "frequency": scheduled_search.frequency,
                "date_filter_days": scheduled_search.date_filter_days
            }
        else:
            # MANUAL SEARCH with consistent formatting
            print(f"Starting enhanced search for: '{request.keywords}' in '{request.location}' (last {request.date_filter_days} days)")
            
            # Step 1: Get existing jobs from database
            existing_jobs = get_existing_jobs_from_db(
                request.keywords, 
                request.location, 
                request.date_filter_days, 
                db
            )
            print(f"Found {len(existing_jobs)} existing jobs in database")
            
            # Step 2: Get fresh jobs from API
            all_api_jobs = []
            page = 1
            max_pages = 20
            
            while page <= max_pages:
                search_params = {
                    "keywords": request.keywords,
                    "location": request.location,
                    "results_per_page": 50,
                    "page": page
                }
                
                jobs_data = await adzuna_client.search_jobs(**search_params)
                page_jobs = jobs_data.get("jobs", [])
                
                if not page_jobs:
                    break
                
                all_api_jobs.extend(page_jobs)
                
                if len(page_jobs) < 50:
                    break
                    
                page += 1
            
            print(f"Retrieved {len(all_api_jobs)} jobs from API")
            
            # Step 3: Apply date filter to API jobs
            if request.date_filter_days:
                filtered_api_jobs = filter_jobs_by_date(all_api_jobs, request.date_filter_days)
            else:
                filtered_api_jobs = all_api_jobs
            
            print(f"After date filtering: {len(filtered_api_jobs)} API jobs")
            
            # Step 4: Combine database jobs with new API jobs (using original formats)
            combined_jobs, new_api_count, db_count = combine_db_and_api_jobs(
                existing_jobs,  # Keep original database objects
                filtered_api_jobs  # Keep original API dictionaries
            )

            
            # Step 5: Format all jobs consistently AFTER combining
            final_formatted_jobs = []
            for job_data in combined_jobs:
                if hasattr(job_data, 'external_id'):
                    # Database job object
                    formatted_job = format_job_for_ui(job_data, source="database")
                else:
                    # API job dictionary
                    formatted_job = format_job_for_ui(job_data, source=job_data.get("source", "api"))
                final_formatted_jobs.append(formatted_job)

            combined_jobs = final_formatted_jobs
            
            print(f"Combined results: {len(combined_jobs)} total jobs ({db_count} from DB, {new_api_count} new from API)")
            
            # Step 6: Store new API jobs in database (using original API data structure)
            search_record = Search(
                keywords=request.keywords,
                location=request.location or "",
                results_count=len(combined_jobs)
            )
            db.add(search_record)
            db.commit()
            db.refresh(search_record)
            
            jobs_stored = 0
            for job_data in filtered_api_jobs:
                # Check for existing job before storing
                existing_job = db.query(Job).filter(
                    and_(
                        Job.external_id == str(job_data.get("id", "")),
                        Job.title == job_data.get("title", ""),
                        Job.company == job_data.get("company", {}).get("display_name", "")
                    )
                ).first()
                
                if not existing_job:
                    # Use consistent formatting when storing
                    formatted_job = format_job_for_ui(job_data, source="api")
                    
                    job = Job(
                        external_id=formatted_job["id"],
                        title=formatted_job["title"],
                        company=formatted_job["company"],
                        location=formatted_job["location"],
                        description=formatted_job["description"][:1000],
                        apply_link=formatted_job["apply_link"],
                        date_posted=formatted_job["date_posted"],
                        salary_range=formatted_job["salary_range"],
                        search_id=search_record.id
                    )
                    db.add(job)
                    jobs_stored += 1
            
            db.commit()
            print(f"Stored {jobs_stored} new jobs in database")
            
            # Return consistently formatted jobs
            return {
                "jobs": combined_jobs,  # Already consistently formatted
                "total_results": len(combined_jobs),
                "search_params": {
                    "keywords": request.keywords,
                    "location": request.location,
                    "date_filter_days": request.date_filter_days
                },
                "result_breakdown": {
                    "from_database": db_count,
                    "new_from_api": new_api_count,
                    "total": len(combined_jobs)
                }
            }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error processing search: {str(e)}")

@app.get("/api/recent-jobs")
async def get_recent_jobs(
    searches_back: int = Query(1, ge=1, le=10),
    db: Session = Depends(get_db)
):
    """Get jobs from recent searches with pagination support"""
    try:
        recent_searches = db.query(Search).order_by(desc(Search.created_at)).limit(searches_back).all()
        
        if not recent_searches:
            return {"searches": [], "jobs": [], "total_jobs": 0}
        
        search_ids = [search.id for search in recent_searches]
        jobs = db.query(Job).filter(Job.search_id.in_(search_ids)).order_by(desc(Job.created_at)).all()
        
        formatted_jobs = []
        for job in jobs:
            formatted_jobs.append({
                "id": job.external_id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "description": job.description,
                "apply_link": job.apply_link,
                "date_posted": job.date_posted,
                "salary_range": job.salary_range,
                "search_keywords": next((s.keywords for s in recent_searches if s.id == job.search_id), ""),
                "search_location": next((s.location for s in recent_searches if s.id == job.search_id), ""),
                "source": "database"
            })
        
        search_info = []
        for search in recent_searches:
            search_info.append({
                "keywords": search.keywords,
                "location": search.location,
                "results_count": search.results_count,
                "created_at": search.created_at.isoformat()
            })
        
        return {
            "searches": search_info,
            "jobs": formatted_jobs,
            "total_jobs": len(formatted_jobs)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recent jobs: {str(e)}")

@app.get("/api/scheduled")
async def get_scheduled_searches(db: Session = Depends(get_db)):
    try:
        scheduled_searches = db.query(ScheduledSearch).order_by(ScheduledSearch.created_at.desc()).all()
        
        return {
            "scheduled_searches": [
                {
                    "id": schedule.id,
                    "keywords": schedule.keywords,
                    "location": schedule.location,
                    "frequency": schedule.frequency,
                    "date_filter_days": schedule.date_filter_days,
                    "is_active": schedule.is_active == "true",
                    "last_run": schedule.last_run.isoformat() if schedule.last_run else None,
                    "next_run": schedule.next_run.isoformat() if schedule.next_run else None,
                    "created_at": schedule.created_at.isoformat()
                }
                for schedule in scheduled_searches
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching scheduled searches: {str(e)}")

@app.delete("/api/scheduled/{schedule_id}")
async def delete_scheduled_search(schedule_id: int, db: Session = Depends(get_db)):
    try:
        scheduled_search = db.query(ScheduledSearch).filter(ScheduledSearch.id == schedule_id).first()
        
        if not scheduled_search:
            raise HTTPException(status_code=404, detail="Scheduled search not found")
        
        job_id = f"scheduled_search_{schedule_id}"
        try:
            scheduler.remove_job(job_id)
        except:
            pass
        
        db.delete(scheduled_search)
        db.commit()
        
        return {"message": "Scheduled search deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting scheduled search: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )