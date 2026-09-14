from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from src.database import get_db
from src.services import job_manager
from src.models import Job
from src.schemas.common import Pagination
from src.schemas.job import JobResponse
from typing import Optional

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])

@router.post("/generate", status_code=201)
def generate_jobs(db: Session = Depends(get_db)):
    result = job_manager.generate_jobs(db)
    if result["jobs_created"] == 0:
        # FastAPI lets us return 200 for unchanged state if we want, 
        # but 201 is specified in contract when jobs are generated.
        pass 
    return result

@router.get("", response_model=Pagination[JobResponse])
def get_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
        
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    total_pages = (total + page_size - 1) // page_size
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }

@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
