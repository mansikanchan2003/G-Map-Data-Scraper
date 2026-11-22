"""System health for the Dashboard: are the website, the worker and the scraper alive (22 Nov 2026)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import User
from src.routers.auth import current_user
from src.services import system_health

router = APIRouter(prefix="/api/v1/system", tags=["System"])

# Error lines can name a business or a run; the team sees them, view-only members see the rest.
TEAM = ("admin", "manager", "operator")


@router.get("/health")
def health(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return system_health.report(db, show_errors=user.role in TEAM)
