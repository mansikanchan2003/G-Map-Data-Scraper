"""
Template Studio: the agent makes WhatsApp templates, a person approves them.

Generation runs in the background because one variant takes a minute or more
(copy, several photo attempts, rendering). The endpoints return the placeholder
rows immediately and the Studio polls until they are ready.

Nothing here contacts Meta except /approve.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.user import User
from src.models.whatsapp import WhatsAppTemplate
from src.routers.auth import current_user
from src.services import creative_brief, template_studio
from src.services.gemini_client import GeminiClient

router = APIRouter(prefix="/api/v1/whatsapp/studio", tags=["Template Studio"])


class StudioDraft(BaseModel):
    template_id: str
    name: str
    status: str
    target_state: Optional[str] = None
    language_code: Optional[str] = None
    category: Optional[str] = None
    header_type: Optional[str] = None
    header_content: Optional[str] = None
    body: str
    footer: Optional[str] = None
    buttons: Optional[List[dict]] = None
    meta_template_name: Optional[str] = None
    generation: Optional[dict] = None
    review_note: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class GenerateRequest(BaseModel):
    state: str
    count: int = Field(2, ge=1, le=template_studio.MAX_VARIANTS)
    brief: Optional[str] = Field(None, max_length=1000)


class DraftEdit(BaseModel):
    body: Optional[str] = None
    footer: Optional[str] = None
    apply_button: Optional[str] = None
    callback_button: Optional[str] = None
    poster: Optional[dict] = None


class ApproveRequest(BaseModel):
    category: str = "MARKETING"


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=1000)


def _draft(db: Session, template_id: str) -> WhatsAppTemplate:
    tmpl = db.query(WhatsAppTemplate).filter(
        WhatsAppTemplate.template_id == template_id,
        WhatsAppTemplate.origin == "agent",
    ).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="No such Studio template")
    return tmpl


@router.get("/status")
def studio_status():
    """Whether the agent can run, so the Studio can say why before anyone clicks."""
    client = GeminiClient()
    if not client.is_configured():
        return {"ready": False, "error": "GEMINI_API_KEY is not set on the server."}
    return {"ready": True, "error": None}


@router.get("/rules")
def studio_rules():
    return creative_brief.rules_for_display()


@router.get("/states")
def studio_states(db: Session = Depends(get_db)):
    return template_studio.targeted_states(db)


@router.get("/performance")
def studio_performance(db: Session = Depends(get_db)):
    return template_studio.template_performance(db)


@router.get("/drafts", response_model=List[StudioDraft])
def list_drafts(db: Session = Depends(get_db)):
    return (
        db.query(WhatsAppTemplate)
        .filter(WhatsAppTemplate.origin == "agent")
        .order_by(WhatsAppTemplate.created_at.desc())
        .limit(100).all()
    )


@router.post("/generate", response_model=List[StudioDraft])
def generate(req: GenerateRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not creative_brief.language_for_state(req.state):
        raise HTTPException(
            status_code=400,
            detail=f"No language is set for {req.state}. Add it to STATE_LANGUAGES in creative_brief.py.",
        )
    if not GeminiClient().is_configured():
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not set on the server.")

    rows = template_studio.create_placeholders(db, req.state, req.count, req.brief)
    background.add_task(
        template_studio.run_generation, [r.template_id for r in rows], req.state, req.brief
    )
    return rows


@router.post("/drafts/{template_id}/new-photo", response_model=StudioDraft)
def new_photo(template_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    tmpl = _draft(db, template_id)
    has_copy = bool((tmpl.generation or {}).get("poster") and (tmpl.generation or {}).get("photo_scene"))
    # A failed draft whose copy survived can be finished once photos work.
    retryable = tmpl.status == template_studio.GENERATION_FAILED and has_copy
    if tmpl.status != template_studio.AWAITING_APPROVAL and not retryable:
        raise HTTPException(status_code=409, detail="Only a draft awaiting approval, or one whose photo failed, can get a new photo")
    tmpl.status = template_studio.GENERATING
    db.commit()
    background.add_task(template_studio.run_new_photo, template_id)
    return tmpl


@router.patch("/drafts/{template_id}")
def edit_draft(template_id: str, edit: DraftEdit, db: Session = Depends(get_db)):
    tmpl = _draft(db, template_id)
    if tmpl.status != template_studio.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Only a draft awaiting approval can be edited here")
    unknown = set(edit.poster or {}) - set(template_studio.POSTER_FIELDS) - {"benefits"}
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown poster fields: {', '.join(sorted(unknown))}")
    try:
        warnings = template_studio.update_draft(
            db, tmpl, edit.body, edit.footer,
            {"apply_button": edit.apply_button, "callback_button": edit.callback_button},
            edit.poster,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"Could not apply the edit: {e}")
    db.refresh(tmpl)
    return {"draft": StudioDraft.model_validate(tmpl), "warnings": warnings}


@router.post("/drafts/{template_id}/approve")
def approve_draft(template_id: str, req: ApproveRequest = None,
                  db: Session = Depends(get_db), user: User = Depends(current_user)):
    tmpl = _draft(db, template_id)
    if tmpl.status != template_studio.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail=f"This draft is {tmpl.status}, not awaiting approval")
    category = ((req.category if req else None) or "MARKETING").upper()
    result = template_studio.approve(db, tmpl, user.email, category)
    db.refresh(tmpl)
    return {
        "status": result["status"],
        "error": result.get("error"),
        "draft": StudioDraft.model_validate(tmpl),
    }


@router.post("/drafts/{template_id}/reject", response_model=StudioDraft)
def reject_draft(template_id: str, req: RejectRequest,
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    tmpl = _draft(db, template_id)
    if tmpl.status not in (template_studio.AWAITING_APPROVAL, template_studio.GENERATION_FAILED):
        raise HTTPException(status_code=409, detail=f"This draft is {tmpl.status} and cannot be rejected")
    template_studio.reject(db, tmpl, user.email, req.reason)
    return tmpl
