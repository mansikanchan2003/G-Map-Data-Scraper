"""Partner organisations near SBI branches; see services/partners.py."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.database import get_db
from src.services import partners

router = APIRouter(prefix="/api/v1/partners", tags=["Partner Organisations"])


@router.get("")
def list_partner_organisations(
    type: Optional[str] = Query(None, max_length=200),
    branch: Optional[str] = Query(None, max_length=10),
    q: Optional[str] = Query(None, max_length=100),
    db: Session = Depends(get_db),
):
    """NGOs, RSETIs, SHGs and others found at SBI branch PIN codes, with each one's branch."""
    return partners.list_partners(db, kind=type, branch=branch, q=q)
