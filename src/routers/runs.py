from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from src.database import get_db
from src.models import RunLog
from src.schemas.common import Pagination
from src.schemas.run_log import RunLogResponse
from typing import Optional

router = APIRouter(prefix="/api/v1/runs", tags=["Runs"])

@router.get("", response_model=Pagination[RunLogResponse])
def get_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(RunLog)
    if status:
        query = query.filter(RunLog.status == status)
        
    query = query.order_by(RunLog.started_at.desc())
    
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

@router.get("/{run_id}", response_model=RunLogResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(RunLog).filter(RunLog.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run log not found")
    return run
