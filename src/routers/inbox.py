"""
The WhatsApp inbox: conversations with the business number, and replying.

A conversation exists once someone has written to the number — a typed
message, a quick-reply tap, anything. Its thread also shows the campaign
messages that reached the same number, so a reply is read next to what it
answers.

Phone numbers appear in paths as digits only ("919876543210"): a "+" in a
path is easy to lose to URL encoding.
"""
import logging
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import Business
from src.models.inbox import OnboardingDocument, WhatsAppConversation, WhatsAppMessage
from src.models.user import User
from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient, WhatsAppTemplate
from src.routers.auth import current_user
from src.services import drive_uploads, inbox, onboarding_bot

logger = logging.getLogger("gmap_scraper.inbox")

router = APIRouter(prefix="/api/v1/inbox", tags=["WhatsApp Inbox"])


class ConversationSummary(BaseModel):
    phone: str
    name: Optional[str] = None
    last_message: Optional[str] = None
    last_direction: Optional[str] = None
    last_message_at: Optional[datetime] = None
    unread: int = 0
    window_expires_at: Optional[datetime] = None
    bot_step: Optional[str] = None
    bot_step_label: Optional[str] = None
    bot_paused: bool = False
    documents: int = 0


class ThreadMessage(BaseModel):
    id: str
    direction: str
    # text, button, interactive, image, ... ; for OUT also buttons, link, and
    # campaign for a template sent by a campaign.
    kind: str
    body: Optional[str] = None
    payload: Optional[object] = None
    status: Optional[str] = None
    error_reason: Optional[str] = None
    sent_by: Optional[str] = None
    campaign: Optional[str] = None
    created_at: datetime


class DocumentInfo(BaseModel):
    document_id: str
    doc_type: str
    label: str
    original_name: Optional[str] = None
    content_type: str
    size_bytes: int
    uploaded_at: datetime
    drive_url: Optional[str] = None
    drive_error: Optional[str] = None


class ConversationDetail(ConversationSummary):
    category: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    bot_data: Optional[dict] = None
    documents_submitted_at: Optional[datetime] = None
    upload_url: Optional[str] = None
    drive_folder_url: Optional[str] = None
    messages: List[ThreadMessage] = []
    document_files: List[DocumentInfo] = []


class SendRequest(BaseModel):
    message: str


class BotStateRequest(BaseModel):
    paused: bool


class BotSettings(BaseModel):
    enabled: bool
    triggers: List[str] = Field(default_factory=list)


class BotSettingsResponse(BotSettings):
    radius_km: float
    documents: List[dict]
    public_base_url_set: bool
    drive_configured: bool
    # Who the Drive folder must be shared with.
    drive_service_account: Optional[str] = None


def _phone(digits: str) -> str:
    phone = inbox.normalize_phone(digits)
    if not phone:
        raise HTTPException(status_code=400, detail="Not a phone number")
    return phone


def _get_conversation(db: Session, digits: str) -> WhatsAppConversation:
    conv = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == _phone(digits)).first()
    if conv is None:
        raise HTTPException(status_code=404, detail="No conversation with this number")
    return conv


def _names(db: Session, phones: list) -> dict:
    """A name for each number: the campaign recipient's, else the business's."""
    if not phones:
        return {}
    names = {}
    for b in db.query(Business.phone, Business.name).filter(Business.phone.in_(phones)).all():
        names.setdefault(b.phone, b.name)
    rows = (db.query(WhatsAppCampaignRecipient.phone, WhatsAppCampaignRecipient.name)
            .filter(WhatsAppCampaignRecipient.phone.in_(phones),
                    WhatsAppCampaignRecipient.name.isnot(None))
            .order_by(WhatsAppCampaignRecipient.created_at.asc()).all())
    for r in rows:
        names[r.phone] = r.name  # the latest campaign's name wins
    return names


def _unread(db: Session, convs: list) -> dict:
    if not convs:
        return {}
    epoch = datetime(1970, 1, 1)
    out = {}
    for conv in convs:
        since = conv.last_read_at or epoch
        out[conv.phone] = since
    rows = (db.query(WhatsAppMessage.phone, WhatsAppMessage.created_at)
            .filter(WhatsAppMessage.phone.in_(list(out)), WhatsAppMessage.direction == "IN")
            .all())
    counts = {}
    for phone, at in rows:
        if inbox.aware(at) > inbox.aware(out[phone]):
            counts[phone] = counts.get(phone, 0) + 1
    return counts


def _summary(conv, name, last, unread, docs) -> dict:
    return dict(
        phone=conv.phone,
        name=conv.profile_name or name,
        last_message=(last.body if last else None),
        last_direction=(last.direction if last else None),
        last_message_at=inbox.aware(conv.last_message_at),
        unread=unread,
        window_expires_at=inbox.window_expires_at(conv),
        bot_step=conv.bot_step,
        bot_step_label=onboarding_bot.STEP_LABELS.get(conv.bot_step),
        bot_paused=bool(conv.bot_paused),
        documents=docs,
    )


@router.get("/conversations", response_model=List[ConversationSummary])
def list_conversations(
    q: Optional[str] = Query(None, max_length=100),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Conversations, most recent first. `q` matches a number or a name."""
    query = db.query(WhatsAppConversation)
    if q and q.strip():
        term = q.strip()
        digits = "".join(ch for ch in term if ch.isdigit())
        conds = [WhatsAppConversation.profile_name.ilike(f"%{term}%")]
        if digits:
            conds.append(WhatsAppConversation.phone.like(f"%{digits}%"))
        from sqlalchemy import or_
        query = query.filter(or_(*conds))
    convs = (query.order_by(WhatsAppConversation.last_message_at.desc().nullslast())
             .limit(limit).all())
    if not convs:
        return []
    phones = [c.phone for c in convs]

    latest = (db.query(WhatsAppMessage.phone, func.max(WhatsAppMessage.created_at).label("at"))
              .filter(WhatsAppMessage.phone.in_(phones))
              .group_by(WhatsAppMessage.phone).subquery())
    last_by_phone = {}
    for m in (db.query(WhatsAppMessage)
              .join(latest, (WhatsAppMessage.phone == latest.c.phone)
                    & (WhatsAppMessage.created_at == latest.c.at)).all()):
        last_by_phone[m.phone] = m

    docs = dict(db.query(OnboardingDocument.phone, func.count(OnboardingDocument.document_id))
                .filter(OnboardingDocument.phone.in_(phones))
                .group_by(OnboardingDocument.phone).all())
    names = _names(db, phones)
    unread = _unread(db, convs)

    return [ConversationSummary(**_summary(
        c, names.get(c.phone), last_by_phone.get(c.phone), unread.get(c.phone, 0), docs.get(c.phone, 0),
    )) for c in convs]


@router.get("/summary")
def inbox_summary(db: Session = Depends(get_db)):
    """How many conversations have something unread, for the sidebar badge."""
    convs = db.query(WhatsAppConversation).all()
    unread = _unread(db, convs)
    return {"unread_conversations": sum(1 for n in unread.values() if n)}


def _thread(db: Session, phone: str) -> List[ThreadMessage]:
    items = [ThreadMessage(
        id=m.message_id, direction=m.direction, kind=m.kind, body=m.body, payload=m.payload,
        status=m.status, error_reason=m.error_reason, sent_by=m.sent_by, created_at=inbox.aware(m.created_at),
    ) for m in db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == phone).all()]

    # The campaign messages this number was sent, so a reply sits under what
    # it answers. Ones never handed to Meta are left out.
    sends = (db.query(WhatsAppCampaignRecipient, WhatsAppCampaign, WhatsAppTemplate)
             .join(WhatsAppCampaign, WhatsAppCampaign.campaign_id == WhatsAppCampaignRecipient.campaign_id)
             .outerjoin(WhatsAppTemplate, WhatsAppTemplate.template_id == WhatsAppCampaign.template_id)
             .filter(WhatsAppCampaignRecipient.phone == phone,
                     WhatsAppCampaignRecipient.provider_message_id.isnot(None))
             .all())
    for r, campaign, template in sends:
        items.append(ThreadMessage(
            id=r.recipient_id, direction="OUT", kind="campaign",
            body=template.body if template else None,
            payload=[b.get("text") for b in (template.buttons or []) if isinstance(b, dict) and b.get("text")]
            if template else None,
            status=r.status, error_reason=r.reason, sent_by="campaign", campaign=campaign.name,
            created_at=inbox.aware(r.sent_at or r.created_at),
        ))

    items.sort(key=lambda m: m.created_at)
    return items


@router.get("/conversations/{digits}", response_model=ConversationDetail)
def get_conversation(digits: str, db: Session = Depends(get_db)):
    conv = _get_conversation(db, digits)
    business = db.query(Business).filter(Business.phone == conv.phone).first()
    names = _names(db, [conv.phone])
    messages = _thread(db, conv.phone)
    last = next((m for m in reversed(messages) if m.kind != "campaign"), None)
    files = (db.query(OnboardingDocument).filter(OnboardingDocument.phone == conv.phone)
             .order_by(OnboardingDocument.uploaded_at.asc()).all())
    labels = {d["key"]: d["label"] for d in onboarding_bot.DOCUMENTS}

    summary = _summary(conv, names.get(conv.phone), None, _unread(db, [conv]).get(conv.phone, 0), len(files))
    summary["last_message"] = last.body if last else None
    summary["last_direction"] = last.direction if last else None

    token_live = conv.upload_token and inbox.aware(conv.upload_token_expires_at) and \
        inbox.aware(conv.upload_token_expires_at) > inbox.now()
    return ConversationDetail(
        **summary,
        category=business.category if business else None,
        district=business.district if business else None,
        state=business.state if business else None,
        bot_data=conv.bot_data,
        documents_submitted_at=inbox.aware(conv.documents_submitted_at),
        upload_url=onboarding_bot.upload_url(conv) if token_live else None,
        drive_folder_url=conv.drive_folder_url,
        messages=messages,
        document_files=[DocumentInfo(
            document_id=f.document_id, doc_type=f.doc_type, label=labels.get(f.doc_type, f.doc_type),
            original_name=f.original_name, content_type=f.content_type,
            size_bytes=f.size_bytes, uploaded_at=inbox.aware(f.uploaded_at),
            drive_url=f.drive_url, drive_error=f.drive_error,
        ) for f in files],
    )


@router.post("/conversations/{digits}/messages", response_model=ThreadMessage)
def send_message(
    digits: str,
    payload: SendRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Reply with a typed message, from the business number.

    Meta allows this only within 24 hours of the person's last message, so the
    window is checked here and the refusal explains itself, instead of
    Meta's 131047 coming back after the fact.
    """
    body = (payload.message or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message is empty")
    if len(body) > 4096:
        raise HTTPException(status_code=400, detail="Message is longer than 4096 characters")

    conv = _get_conversation(db, digits)
    if not inbox.window_open(conv):
        expires = inbox.window_expires_at(conv)
        raise HTTPException(
            status_code=409,
            detail=("The 24-hour reply window closed"
                    + (f" at {expires.strftime('%d %b, %H:%M UTC')}" if expires else "")
                    + ". Only an approved template can reach this number now."),
        )

    msg = inbox.send(db, conv.phone, body, sent_by=user.email)
    # Someone answering by hand has read the conversation.
    conv.last_read_at = inbox.now()
    db.commit()
    if msg.status == "FAILED":
        raise HTTPException(status_code=502, detail=msg.error_reason)
    return ThreadMessage(
        id=msg.message_id, direction=msg.direction, kind=msg.kind, body=msg.body,
        status=msg.status, sent_by=msg.sent_by, created_at=inbox.aware(msg.created_at),
    )


@router.post("/conversations/{digits}/read")
def mark_read(digits: str, db: Session = Depends(get_db)):
    conv = _get_conversation(db, digits)
    conv.last_read_at = inbox.now()
    db.commit()
    return {"status": "ok"}


@router.post("/conversations/{digits}/bot")
def set_bot_state(digits: str, payload: BotStateRequest, db: Session = Depends(get_db)):
    """Pause the bot to answer by hand, or let it carry on."""
    conv = _get_conversation(db, digits)
    conv.bot_paused = payload.paused
    db.commit()
    return {"bot_paused": conv.bot_paused}


@router.get("/bot-settings", response_model=BotSettingsResponse)
def get_bot_settings(db: Session = Depends(get_db)):
    cfg = onboarding_bot.get_settings(db)
    from src.services.pincode_coverage import RADIUS_KM
    return BotSettingsResponse(
        **cfg, radius_km=RADIUS_KM, documents=onboarding_bot.DOCUMENTS,
        public_base_url_set=bool((os.environ.get("PUBLIC_BASE_URL") or "").strip()),
        drive_configured=drive_uploads.configured(),
        drive_service_account=drive_uploads.service_account_email(),
    )


@router.put("/bot-settings", response_model=BotSettingsResponse)
def update_bot_settings(payload: BotSettings, db: Session = Depends(get_db)):
    if payload.enabled and not [t for t in payload.triggers if t.strip()]:
        raise HTTPException(status_code=400, detail="Name at least one button that starts the bot")
    onboarding_bot.save_settings(db, payload.enabled, payload.triggers)
    return get_bot_settings(db)


@router.get("/documents/{document_id}")
def get_document(document_id: str, download: bool = False, db: Session = Depends(get_db)):
    doc = db.query(OnboardingDocument).filter(OnboardingDocument.document_id == document_id).first()
    # Once in Drive the local copy is gone; Drive decides who may open it.
    if doc is not None and doc.drive_url and not os.path.isfile(doc.stored_path):
        return RedirectResponse(doc.drive_url, status_code=302)
    if doc is None or not os.path.isfile(doc.stored_path):
        raise HTTPException(status_code=404, detail="Document not found")
    name = doc.original_name or os.path.basename(doc.stored_path)
    return FileResponse(
        doc.stored_path, media_type=doc.content_type, filename=name,
        content_disposition_type="attachment" if download else "inline",
    )


@router.post("/conversations/{digits}/drive")
def save_to_drive(digits: str, db: Session = Depends(get_db)):
    """Copy this person's documents to Google Drive again, after a failure."""
    conv = _get_conversation(db, digits)
    try:
        copied = drive_uploads.save_conversation(db, conv)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:500])
    failed = db.query(OnboardingDocument).filter(
        OnboardingDocument.phone == conv.phone, OnboardingDocument.drive_file_id.is_(None)).count()
    if failed:
        raise HTTPException(status_code=502, detail=f"{failed} file(s) could not be copied to Drive")
    return {"copied": copied, "folder_url": conv.drive_folder_url}
