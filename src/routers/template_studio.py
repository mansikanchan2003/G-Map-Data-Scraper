"""
Template Studio: the agent makes WhatsApp templates, a person approves them.

Generation runs in the background because one variant takes a minute or more
(copy, several photo attempts, rendering). The endpoints return the placeholder
rows immediately and the Studio polls until they are ready.

Nothing here contacts Meta except /approve, and /from-messages, whose
templates are the team's own wording rather than the agent's.
"""
import logging
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
logger = logging.getLogger("gmap_scraper.template_studio")


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


@router.get("/image-allowance")
def image_allowance(db: Session = Depends(get_db)):
    """How many free images can still be made today, and when the limit resets."""
    from src.services import image_prompts
    return image_prompts.allowance(db)


@router.get("/image-prompts")
def image_prompt_record(db: Session = Depends(get_db)):
    """Which image prompts have worked: per style, and the latest images asked for."""
    from src.services import image_prompts
    return image_prompts.summary(db)


@router.get("/drafts", response_model=List[StudioDraft])
def list_drafts(db: Session = Depends(get_db)):
    """The poster agent's drafts. The business agent's have their own list."""
    from src.services import business_agent

    rows = (
        db.query(WhatsAppTemplate)
        .filter(WhatsAppTemplate.origin == "agent")
        .order_by(WhatsAppTemplate.created_at.desc())
        .limit(200).all()
    )
    return [t for t in rows if not business_agent.is_business_draft(t)][:100]


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
    has_copy = template_studio.can_make_header(tmpl.generation or {})
    # A failed draft whose copy survived can be finished once photos work, and
    # one waiting for the image allowance can be tried now rather than later.
    waiting = tmpl.status == template_studio.PHOTO_PENDING
    retryable = tmpl.status == template_studio.GENERATION_FAILED and has_copy
    if tmpl.status != template_studio.AWAITING_APPROVAL and not (retryable or waiting):
        raise HTTPException(status_code=409, detail="Only a draft awaiting approval, or one whose photo failed, can get a new photo")
    tmpl.status = template_studio.GENERATING
    db.commit()
    # A waiting draft keeps the sign photo it already tried.
    background.add_task(template_studio.run_new_photo, template_id, not waiting)
    return tmpl


@router.patch("/drafts/{template_id}")
def edit_draft(template_id: str, edit: DraftEdit, db: Session = Depends(get_db)):
    tmpl = _draft(db, template_id)
    if tmpl.status != template_studio.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Only a draft awaiting approval can be edited here")
    unknown = set(edit.poster or {}) - set(template_studio.POSTER_FIELDS) - {"benefits"}
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown poster fields: {', '.join(sorted(unknown))}")
    from src.services import business_agent

    buttons = {"apply_button": edit.apply_button, "callback_button": edit.callback_button}
    try:
        if business_agent.is_business_draft(tmpl):
            # No poster to re-render: the text is the whole template.
            warnings = business_agent.update(db, tmpl, edit.body, edit.footer, buttons)
        else:
            warnings = template_studio.update_draft(db, tmpl, edit.body, edit.footer, buttons, edit.poster)
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
    if tmpl.status not in (template_studio.AWAITING_APPROVAL, template_studio.GENERATION_FAILED,
                           template_studio.PHOTO_PENDING):
        raise HTTPException(status_code=409, detail=f"This draft is {tmpl.status} and cannot be rejected")
    template_studio.reject(db, tmpl, user.email, req.reason)
    return tmpl


# --- From a messages sheet ---------------------------------------------------
# Unlike the agent's drafts above, these are worded by the team already: the
# template is read back out of messages written for each person, and goes to
# Meta without waiting for an Approve click. See src/services/sheet_templates.py.

from src.services import sheet_templates  # noqa: E402


class FromMessagesRequest(BaseModel):
    # One dict per sheet row, keyed by the sheet's own headers.
    rows: List[dict] = Field(..., min_length=1, max_length=sheet_templates.MAX_ROWS)
    message_column: str = Field(..., min_length=1)
    phone_column: str = Field(..., min_length=1)
    category: str = "MARKETING"
    language: str = "en_US"
    # The file it came from, which names the template.
    source_name: Optional[str] = Field(None, max_length=200)
    # The tracked "Apply Now" button, and where its visits are forwarded.
    # The link normally goes in the message text; a button is optional.
    add_button: bool = False
    button_text: Optional[str] = Field(None, max_length=sheet_templates.BUTTON_TEXT_LIMIT)
    link_target: Optional[str] = Field(None, max_length=500)


@router.post("/from-messages")
def template_from_messages(req: FromMessagesRequest, db: Session = Depends(get_db),
                           user: User = Depends(current_user)):
    """
    Turns a sheet of written-out messages into one template, and makes sure
    Meta has it.

    Call it again with the same sheet to learn where Meta's review has got
    to: it finds the earlier submission rather than making another.
    """
    category = req.category.upper()
    if category not in ("MARKETING", "UTILITY"):
        raise HTTPException(status_code=400, detail="Category must be MARKETING or UTILITY.")
    try:
        out = sheet_templates.template_from_messages(
            db, req.rows, req.message_column, req.phone_column,
            category=category, language=req.language, source_name=req.source_name,
            link_target=req.link_target, button_text=req.button_text, add_button=req.add_button,
        )
    except sheet_templates.DerivationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    logger.info(f"template_studio event=SHEET_TEMPLATE action={out['action']} by={user.email} "
                f"rows={len(req.rows)} source={req.source_name!r}")
    return {
        "action": out["action"],
        "reason": out["reason"],
        "derived": out["derived"],
        "template": sheet_templates.describe(out["template"]) if out["template"] else None,
    }


@router.get("/sheet-settings")
def sheet_settings():
    """Defaults for the sheet form, and whether visits can be tracked here."""
    return {
        "tracking_enabled": sheet_templates.tracking_enabled(),
        "default_link_target": sheet_templates.DEFAULT_LINK_TARGET,
        "default_button_text": sheet_templates.DEFAULT_BUTTON_TEXT,
        "button_text_limit": sheet_templates.BUTTON_TEXT_LIMIT,
        "max_rows": sheet_templates.MAX_ROWS,
    }


@router.get("/sheet-templates")
def sheet_template_list(db: Session = Depends(get_db)):
    """Templates made from sheets, with Meta's review state kept current."""
    return [sheet_templates.describe(t) for t in sheet_templates.list_sheet_templates(db)]



# --- The business agent ------------------------------------------------------
# Writes templates addressed to scraped businesses, learning from how earlier
# templates did. Its drafts wait for Approve like the poster agent's above.

from src.services import business_agent  # noqa: E402


class BusinessDraftRequest(BaseModel):
    # One dict per business, keyed by the export's headers (name, category,
    # district, state...). Only the details are read; nothing is sent.
    rows: List[dict] = Field(..., min_length=1, max_length=business_agent.MAX_ROWS)
    count: int = Field(2, ge=1, le=business_agent.MAX_VARIANTS)
    brief: Optional[str] = Field(None, max_length=1000)
    # Defaults to the language of the businesses' main state.
    language: Optional[str] = None
    link_target: Optional[str] = Field(None, max_length=500)
    source_name: Optional[str] = Field(None, max_length=200)


@router.post("/business-drafts", response_model=List[StudioDraft])
def write_business_drafts(req: BusinessDraftRequest, background: BackgroundTasks,
                          db: Session = Depends(get_db), user: User = Depends(current_user)):
    """
    Starts the agent writing templates for these businesses. The rows come
    back at once, GENERATING; the Studio polls until they await approval.
    """
    if not GeminiClient().is_configured():
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not set on the server, so the agent cannot write.")
    try:
        summary = business_agent.summarise(req.rows)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    language = business_agent.language_for(summary, req.language)
    link_target = (req.link_target or sheet_templates.DEFAULT_LINK_TARGET).strip()
    if not link_target.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="The link must be a full web address starting with https://.")

    rows = business_agent.create_placeholders(db, summary, req.count, req.brief, language,
                                              link_target, req.source_name)
    background.add_task(business_agent.run_generation, [r.template_id for r in rows])
    logger.info(f"template_studio event=BUSINESS_ROUND by={user.email} rows={summary['rows']} "
                f"state={summary.get('main_state')} language={language} variants={req.count}")
    return rows


@router.get("/business-drafts", response_model=List[StudioDraft])
def list_business_drafts(db: Session = Depends(get_db)):
    """The business agent's drafts, with Meta's review kept current once approved."""
    return business_agent.list_drafts(db)
