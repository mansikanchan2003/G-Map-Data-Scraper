"""The Applications tab: onboarding applications, their qualification and the team's comments."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import User
from src.routers.auth import current_user
from src.services import applications, inbox

router = APIRouter(prefix="/api/v1/applications", tags=["Applications"])


class CommentIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)


def _phone(digits: str) -> str:
    return inbox.normalize_phone(digits)


@router.get("")
def list_applications(removed: bool = False, db: Session = Depends(get_db)):
    """Applications with their totals; removed=true lists the ones taken off the tab."""
    return applications.list_applications(db, removed=removed)


@router.post("/{digits}/comments")
def add_comment(digits: str, payload: CommentIn, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    try:
        c = applications.add_comment(db, _phone(digits), payload.body, user.full_name or user.email)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"comment_id": c.comment_id, "body": c.body, "author": c.author,
            "created_at": applications._iso(c.created_at)}


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str, db: Session = Depends(get_db)):
    try:
        applications.delete_comment(db, comment_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "deleted"}


@router.delete("/{digits}")
def remove_application(digits: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Takes the application off the tab. The chat and its documents are kept."""
    try:
        applications.remove(db, _phone(digits), user.full_name or user.email)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "removed"}


@router.post("/{digits}/restore")
def restore_application(digits: str, db: Session = Depends(get_db)):
    applications.restore(db, _phone(digits))
    return {"status": "restored"}
