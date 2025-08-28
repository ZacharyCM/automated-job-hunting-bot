from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from dotenv import load_dotenv
from typing import Optional, List
import uvicorn

from database import engine, SessionLocal, get_db
from models import Base, Job, Search
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
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Adzuna client
adzuna_client = AdzunaClient(
    api_key=os.getenv("ADZUNA_API_KEY"),
    app_id=os.getenv("ADZUNA_APP_ID")
)

# Serve static files (client build)
if os.path.exists("../client/dist"):
    app.mount("/static", StaticFiles(directory="../client/dist"), name="static")

@app.get("/")
async def read_root():
    """Serve the main application"""
    if os.path.exists("../client/dist/index.html"):
        return FileResponse("../client/dist/index.html")
    return {"message": "Job Hunting Bot API is running! Visit /docs for API documentation."}

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "Job Hunting Bot API is running",
        "adzuna_configured": bool(os.getenv("ADZUNA_API_KEY") and os.getenv("ADZUNA_APP_ID"))
    }

@app.get("/api/jobs")
async def search_jobs(
    keywords: str = Query(..., description="Job search keywords"),
    location: Optional[str] = Query(None, description="Job location"),
    results_per_page: int = Query(20, ge=1, le=50, description="Number of results per page"),
    page: int = Query(1, ge=1, description="Page number")
):
    """
    Search for jobs using keywords and optional location
    """
    try:
        # Check if API credentials are configured
        if not adzuna_client.api_key or not adzuna_client.app_id:
            raise HTTPException(
                status_code=500,
                detail="Adzuna API credentials not configured. Please set ADZUNA_API_KEY and ADZUNA_APP_ID environment variables."
            )
        
        # Search jobs using Adzuna API
        jobs_data = await adzuna_client.search_jobs(
            keywords=keywords,
            location=location,
            results_per_page=results_per_page,
            page=page
        )
        
        # Store search in database
        db = SessionLocal()
        try:
            search_record = Search(
                keywords=keywords,
                location=location or "",
                results_count=len(jobs_data.get("jobs", []))
            )
            db.add(search_record)
            db.commit()
            
            # Store jobs in database (avoid duplicates)
            stored_jobs = []
            for job_data in jobs_data.get("jobs", []):
                # Check if job already exists
                existing_job = db.query(Job).filter(
                    Job.external_id == job_data.get("id", ""),
                    Job.title == job_data.get("title", ""),
                    Job.company == job_data.get("company", {}).get("display_name", "")
                ).first()
                
                if not existing_job:
                    job = Job(
                        external_id=str(job_data.get("id", "")),
                        title=job_data.get("title", ""),
                        company=job_data.get("company", {}).get("display_name", ""),
                        location=job_data.get("location", {}).get("display_name", ""),
                        description=job_data.get("description", "")[:1000],  # Limit description length
                        apply_link=job_data.get("redirect_url", ""),
                        date_posted=job_data.get("created", ""),
                        salary_range=job_data.get("salary_min") and job_data.get("salary_max") 
                                   and f"${job_data.get('salary_min'):,} - ${job_data.get('salary_max'):,}" or None,
                        search_id=search_record.id
                    )
                    db.add(job)
                    stored_jobs.append(job)
                else:
                    stored_jobs.append(existing_job)
            
            db.commit()
            
        finally:
            db.close()
        
        # Format response
        formatted_jobs = []
        for job_data in jobs_data.get("jobs", []):
            formatted_job = {
                "id": job_data.get("id", ""),
                "title": job_data.get("title", ""),
                "company": job_data.get("company", {}).get("display_name", ""),
                "location": job_data.get("location", {}).get("display_name", ""),
                "description": job_data.get("description", ""),
                "apply_link": job_data.get("redirect_url", ""),
                "date_posted": job_data.get("created", ""),
                "salary_range": None
            }
            
            # Add salary info if available
            if job_data.get("salary_min") and job_data.get("salary_max"):
                formatted_job["salary_range"] = f"${job_data.get('salary_min'):,} - ${job_data.get('salary_max'):,}"
            elif job_data.get("salary_min"):
                formatted_job["salary_range"] = f"${job_data.get('salary_min'):,}+"
                
            formatted_jobs.append(formatted_job)
        
        return {
            "jobs": formatted_jobs,
            "total_results": jobs_data.get("count", 0),
            "page": page,
            "results_per_page": results_per_page,
            "search_params": {
                "keywords": keywords,
                "location": location
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error searching jobs: {str(e)}"
        )

@app.get("/api/searches")
async def get_recent_searches(limit: int = Query(10, ge=1, le=50)):
    """Get recent job searches"""
    db = SessionLocal()
    try:
        searches = db.query(Search).order_by(Search.created_at.desc()).limit(limit).all()
        return {
            "searches": [
                {
                    "id": search.id,
                    "keywords": search.keywords,
                    "location": search.location,
                    "results_count": search.results_count,
                    "created_at": search.created_at.isoformat()
                }
                for search in searches
            ]
        }
    finally:
        db.close()

@app.delete("/api/searches/{search_id}")
async def delete_search(search_id: int):
    """Delete a search and its associated jobs"""
    db = SessionLocal()
    try:
        search = db.query(Search).filter(Search.id == search_id).first()
        if not search:
            raise HTTPException(status_code=404, detail="Search not found")
        
        # Delete associated jobs
        db.query(Job).filter(Job.search_id == search_id).delete()
        # Delete search
        db.delete(search)
        db.commit()
        
        return {"message": "Search deleted successfully"}
    finally:
        db.close()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )