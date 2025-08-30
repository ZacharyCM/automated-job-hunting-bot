Job Hunting Bot
An intelligent automated job search platform that combines real-time API data with persistent database storage to deliver comprehensive job matching for engineering and technical positions.
Features
Core Search Capabilities

Advanced Keyword Matching: Search with intelligent term normalization (e.g., "software engineer" matches "developer", "programmer", "SWE")
Comprehensive Results: Combines existing database jobs with fresh API results to maximize coverage
Smart Deduplication: Automatically removes duplicate listings while preserving unique opportunities
Date-Based Filtering: Filter jobs by posting date (1 day to 12 months)
Location Support: Optional location-based job filtering

Automated Search System

Flexible Scheduling: Set automated searches with frequencies from every minute to weekly
Persistent Background Processing: Continues searching even when you're not actively using the platform
Real-time Notifications: Instant UI updates when new automated search results are found
Auto-population: Latest automated results automatically populate your search interface

Data Management

Intelligent Database Storage: Jobs are stored locally to build a comprehensive searchable archive
Source Tracking: Clear indicators showing which jobs are from your database vs fresh from API
Result Analytics: Detailed breakdown showing database vs new API job counts
Search History: Access to previous search results and patterns

User Interface

Responsive Design: Clean, modern interface that works on all devices
Real-time Updates: Live polling for automated search results without page refresh
Enhanced Job Cards: Rich job displays with company, location, salary, and apply links
Pagination Support: Efficient browsing of large result sets
Visual Source Indicators: Distinguish between database jobs and fresh API results

How to Use
Manual Search

Enter job keywords (e.g., "New Grad Software Engineering", "React Developer")
Optionally specify location and date range
Click "Search Jobs Now" to get combined database + fresh API results
Browse paginated results with source indicators
Click "Apply Now" to go directly to job posting

Automated Search Setup

Use the same search form with your desired keywords and filters
Click "Schedule Search" instead of "Search Jobs Now"
Choose frequency (every minute, hourly, daily, weekly, etc.)
Automated searches run in background and results auto-populate your interface
Manage active schedules in the "Active Scheduled Searches" section

Viewing Results

Database Jobs: Previously found jobs marked with "From Database"
Fresh API Jobs: New jobs marked with "Fresh from API"
Result Breakdown: See exact counts of database vs new jobs
Auto-population: When automated searches complete, results appear automatically

Tech Stack
Backend

Framework: Python FastAPI with async support
Database: PostgreSQL with SQLAlchemy ORM
Job API: Adzuna Jobs API integration
Scheduling: APScheduler for automated background searches
Data Processing: Advanced job matching and deduplication algorithms

Frontend

Core: Vanilla JavaScript with ES6 modules
Build Tool: Vite for development and production builds
Styling: Modern CSS with responsive design
Real-time Features: Automatic polling and UI updates

Infrastructure

Containerization: Docker with multi-stage builds
Database: PostgreSQL with connection pooling
Environment: Docker Compose for local development
Deployment Ready: Railway/cloud platform compatible

Local Development
Prerequisites

Docker and Docker Compose
Adzuna API credentials (free at developer.adzuna.com)

Setup

Clone the repository

bashgit clone [your-repo-url]
cd job-hunting-bot

Create environment file

bashcp .env.example .env
# Add your Adzuna API credentials to .env

Start with Docker Compose

bashdocker-compose up -d

Access the application at http://localhost:8000

Development Commands
bash# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Stop everything
docker-compose down
Architecture
Search Logic Flow

Database Query: Search existing jobs using normalized keyword matching
API Integration: Fetch fresh jobs from Adzuna API with pagination
Date Filtering: Apply user-specified date ranges to API results
Deduplication: Combine database and API jobs, removing duplicates
Storage: Persist only new jobs to database
Response: Return formatted, consistent job objects to frontend

Automated Search System

Scheduler: APScheduler manages background job execution
Persistence: Scheduled searches survive application restarts
Error Handling: Robust error recovery and logging
Resource Management: Limited API pagination for automated searches
UI Integration: Real-time polling delivers results to active users

Database Schema

searches: Search queries and metadata
jobs: Individual job listings with relationships
scheduled_searches: Automated search configurations and scheduling data

Contributing
Code Structure

/server: FastAPI backend with database models and API integration
/client: Frontend JavaScript application with build configuration
docker-compose.yml: Development environment setup
Database migrations handled automatically by SQLAlchemy

Development Guidelines

Follow existing code patterns for consistency
Add comprehensive error handling for external API calls
Test both manual and automated search functionality
Ensure responsive design principles in UI changes

This platform provides a production-ready job search solution that intelligently combines historical data with real-time API results while maintaining excellent user experience through automated background processing.