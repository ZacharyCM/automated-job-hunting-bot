from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Search(Base):
    """
    Model for storing job search queries
    """
    __tablename__ = "searches"
    
    id = Column(Integer, primary_key=True, index=True)
    keywords = Column(String(255), nullable=False, index=True)
    location = Column(String(255), default="")
    results_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to jobs
    jobs = relationship("Job", back_populates="search", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Search(id={self.id}, keywords='{self.keywords}', location='{self.location}')>"

class Job(Base):
    """
    Model for storing individual job listings
    """
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(255), index=True)  # ID from Adzuna API
    title = Column(String(500), nullable=False, index=True)
    company = Column(String(255), nullable=False, index=True)
    location = Column(String(255), nullable=False)
    description = Column(Text)
    apply_link = Column(Text, nullable=False)
    date_posted = Column(String(50))  # Store as string since formats vary
    salary_range = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign key to search
    search_id = Column(Integer, ForeignKey("searches.id"))
    
    # Relationship back to search
    search = relationship("Search", back_populates="jobs")
    
    def __repr__(self):
        return f"<Job(id={self.id}, title='{self.title}', company='{self.company}')>"

class ScheduledSearch(Base):
    """
    Model for storing scheduled/automated searches
    Future feature for automation
    """
    __tablename__ = "scheduled_searches"
    
    id = Column(Integer, primary_key=True, index=True)
    keywords = Column(String(255), nullable=False)
    location = Column(String(255), default="")
    frequency = Column(String(50), default="daily")  # hourly, daily, weekly
    is_active = Column(String(10), default="true")  # Store as string for simplicity
    last_run = Column(DateTime)
    next_run = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ScheduledSearch(id={self.id}, keywords='{self.keywords}', frequency='{self.frequency}')>"