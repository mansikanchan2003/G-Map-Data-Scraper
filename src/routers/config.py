from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.database import get_db
from src.services import config_loader
from src.models import Location, Category
from src.schemas.common import Pagination
from src.schemas.location import LocationResponse
from src.schemas.category import CategoryResponse

router = APIRouter(prefix="/api/v1/config", tags=["Configuration"])

@router.post("/sync")
def sync_configuration(db: Session = Depends(get_db)):
    return config_loader.sync_config(db)

@router.get("/locations", response_model=Pagination[LocationResponse])
def get_locations(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Location)
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

@router.get("/categories", response_model=Pagination[CategoryResponse])
def get_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Category)
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
