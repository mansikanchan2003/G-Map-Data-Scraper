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

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
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
from src.services import handover, tickets
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
    # Reached by an AutoGMap campaign. Only these does the bot answer; the
    # number is shared, and everyone else is another team's to handle.
    from_campaign: bool = False
    # A question waiting for a person; see onboarding_bot.flag.
    needs_attention: bool = False
    attention_reason: Optional[str] = None
    attention_at: Optional[datetime] = None
    # Agent to Human: the person answering by hand while the bot waits, and since when.
    handled_by: Optional[str] = None
    handled_since: Optional[datetime] = None
    # The chat's outcome now: {key, label, note, by, at, source ("team" or "bot")}.
    disposition: Optional[dict] = None


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
    # The open ticket while it needs attention.
    ticket_id: Optional[str] = None


class SendRequest(BaseModel):
    message: str


class BotStateRequest(BaseModel):
    paused: bool


class AttentionRequest(BaseModel):
    # True marks the conversation for a person; False is "Question resolved".
    needed: bool
    reason: Optional[str] = Field(None, max_length=500)
    # Recorded with "Question resolved": how the chat ended up.
    disposition: Optional[str] = Field(None, max_length=40)
    note: Optional[str] = Field(None, max_length=500)


class HandoverRequest(BaseModel):
    # "person": a person takes over and the bot stays quiet; "bot": the bot carries on.
    to: str = Field(..., pattern="^(person|bot)$")
    disposition: Optional[str] = Field(None, max_length=40)
    note: Optional[str] = Field(None, max_length=500)
    # Ask again the question the bot was waiting on (on handing back).
    resume: bool = True


class TeachRequest(BaseModel):
    faq_id: str = Field(..., max_length=40)
    question: str = Field(..., min_length=1, max_length=300)
    # The conversation it came from: the answer comes back in that person's language.
    phone: Optional[str] = Field(None, max_length=20)


class DispositionRequest(BaseModel):
    disposition: str = Field(..., max_length=40)
    note: Optional[str] = Field(None, max_length=500)


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


def _summary(conv, name, last, unread, docs, from_campaign=False) -> dict:
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
        from_campaign=from_campaign,
        needs_attention=bool(conv.needs_attention),
        attention_reason=conv.attention_reason,
        attention_at=inbox.aware(conv.attention_at),
        handled_by=conv.handled_by if conv.bot_paused else None,
        handled_since=inbox.aware(conv.handled_since) if conv.bot_paused else None,
        disposition=handover.current(conv),
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
    ours = inbox.campaign_phones(db, phones)

    return [ConversationSummary(**_summary(
        c, names.get(c.phone), last_by_phone.get(c.phone), unread.get(c.phone, 0), docs.get(c.phone, 0),
        c.phone in ours,
    )) for c in convs]


@router.get("/summary")
def inbox_summary(db: Session = Depends(get_db)):
    """How many conversations have something unread, for the sidebar badge."""
    convs = db.query(WhatsAppConversation).all()
    unread = _unread(db, convs)
    return {"unread_conversations": sum(1 for n in unread.values() if n)}


def _public_payload(m: WhatsAppMessage):
    """The payload as the page may see it: whether a file is held, never where."""
    if not isinstance(m.payload, dict) or "stored" not in m.payload:
        return m.payload
    return {**{k: v for k, v in m.payload.items() if k != "stored"}, "available": True}


def _thread(db: Session, phone: str) -> List[ThreadMessage]:
    items = [ThreadMessage(
        id=m.message_id, direction=m.direction, kind=m.kind, body=m.body, payload=_public_payload(m),
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

    summary = _summary(conv, names.get(conv.phone), None, _unread(db, [conv]).get(conv.phone, 0), len(files),
                       any(m.kind == "campaign" for m in messages))
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
        ticket_id=(lambda t: t.ticket_id if t else None)(tickets.open_ticket(db, conv.phone)) if conv.needs_attention else None,
        messages=messages,
        document_files=[DocumentInfo(
            document_id=f.document_id, doc_type=f.doc_type, label=labels.get(f.doc_type, f.doc_type),
            original_name=f.original_name, content_type=f.content_type,
            size_bytes=f.size_bytes, uploaded_at=inbox.aware(f.uploaded_at),
            drive_url=f.drive_url, drive_error=f.drive_error,
        ) for f in files],
    )


@router.get("/attention-alerts")
def attention_alerts(db: Session = Depends(get_db)):
    """
    Every conversation waiting for a person, newest first: shown on every page
    of the app until someone presses "Question resolved" in the chat.
    """
    convs = (db.query(WhatsAppConversation).filter(WhatsAppConversation.needs_attention.is_(True))
             .order_by(WhatsAppConversation.attention_at.desc()).all())
    names = _names(db, [c.phone for c in convs])
    out = []
    for c in convs:
        ticket = tickets.open_ticket(db, c.phone)
        out.append({"phone": c.phone, "name": c.profile_name or names.get(c.phone),
                    "reason": c.attention_reason, "at": inbox.aware(c.attention_at),
                    "ticket_id": ticket.ticket_id if ticket else None})
    return out


@router.get("/tickets")
def list_tickets(status: Optional[str] = Query(None, pattern="^(open|resolved)$"), db: Session = Depends(get_db)):
    """Every ticket raised, newest first: who raised it, why, and when it was solved."""
    return tickets.history(db, status)


@router.get("/tickets/recently-resolved")
def recently_resolved_tickets(db: Session = Depends(get_db)):
    """Tickets solved in the last two hours, announced across the app."""
    return tickets.recently_resolved(db)


@router.get("/conversations/{digits}/summary")
def get_conversation_summary(digits: str, db: Session = Depends(get_db)):
    """The conversation at a glance: who, how far, what they asked, and what to send next."""
    from src.services import chat_summary
    return chat_summary.summarise(db, _get_conversation(db, digits))


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
    # Someone answering by hand has read the conversation, and has taken it
    # over: the bot stays quiet here until it is handed back.
    conv.last_read_at = inbox.now()
    if msg.status != "FAILED":
        handover.take_over(db, conv, user.email)
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
def set_bot_state(digits: str, payload: BotStateRequest, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    """Pause the bot to answer by hand, or let it carry on (a handover, without asking again)."""
    conv = _get_conversation(db, digits)
    if payload.paused:
        handover.take_over(db, conv, user.email)
    else:
        handover.hand_back(db, conv, user.email, resume=False)
    db.commit()
    return {"bot_paused": conv.bot_paused}


@router.post("/conversations/{digits}/handover")
def hand_over(digits: str, payload: HandoverRequest, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    """
    Agent to Human ("person") or Human to Agent ("bot"). Handing back records
    the disposition, solves an open ticket and lets the bot ask its question again.
    """
    conv = _get_conversation(db, digits)
    if payload.disposition and payload.disposition not in handover.DISPOSITIONS:
        raise HTTPException(status_code=400, detail="Unknown disposition")
    sent = None
    if payload.to == "person":
        handover.take_over(db, conv, user.email)
        if payload.disposition:
            handover.record(db, conv, payload.disposition, user.email, payload.note)
    else:
        sent = handover.hand_back(db, conv, user.email, payload.disposition, payload.note, payload.resume)
    db.commit()
    return {"bot_paused": conv.bot_paused, "handled_by": conv.handled_by, "bot_said": sent,
            "disposition": handover.current(conv)}


@router.post("/conversations/{digits}/disposition")
def set_disposition(digits: str, payload: DispositionRequest, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    """Record how the chat ended up (Interested, Call back later, Not reachable...)."""
    conv = _get_conversation(db, digits)
    try:
        now = handover.record(db, conv, payload.disposition, user.email, payload.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return now


@router.get("/conversations/{digits}/activity")
def chat_activity(digits: str, db: Session = Depends(get_db)):
    """Handovers and dispositions in this chat, oldest first."""
    conv = _get_conversation(db, digits)
    return handover.activity(db, conv.phone)


@router.get("/faq")
def faq_answers(db: Session = Depends(get_db)):
    """Every answer the bot can give, and the questions the team has taught it for each."""
    from src.services import faq_learning
    return faq_learning.answers(db)


@router.post("/faq/teach")
def teach_the_bot(payload: TeachRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """
    Tie a question the bot did not recognise to the answer that covers it, so
    the bot answers it (and questions like it) itself from now on. Returns the
    answer in the person's language, ready to send.
    """
    from src.services import eko_knowledge, faq_learning
    try:
        faq_learning.teach(db, payload.faq_id, payload.question)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    lang = "hi"
    if payload.phone:
        conv = db.get(WhatsAppConversation, inbox.normalize_phone(payload.phone))
        if conv is not None:
            lang = (conv.bot_data or {}).get("lang") or "hi"
    logger.info(f"inbox event=BOT_TAUGHT faq={payload.faq_id} by={user.email}")
    return {"faq_id": payload.faq_id, "answer": eko_knowledge.answer(payload.faq_id, lang, payload.question)}


@router.delete("/faq/teach")
def forget_a_teaching(payload: TeachRequest, db: Session = Depends(get_db)):
    from src.services import faq_learning
    faq_learning.forget(db, payload.faq_id, payload.question)
    return {"status": "ok"}


@router.get("/dispositions")
def disposition_options():
    return handover.options()


@router.get("/dispositions/dashboard")
def disposition_dashboard(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)):
    """Every chat's disposition now, the team's recent ones, and the chats people are handling."""
    return handover.dashboard(db, days)


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


# Shown in the page itself; anything else is only ever downloaded, so a file
# someone sent cannot run as a page on our domain.
_INLINE_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "video/mp4", "video/3gpp",
    "audio/ogg", "audio/mpeg", "audio/mp4", "audio/aac", "audio/amr",
    "application/pdf",
}


@router.get("/media/{message_id}")
def get_media(message_id: str, download: bool = False, db: Session = Depends(get_db)):
    """
    A photo, video, voice note or document someone sent.

    Normally fetched from Meta when it arrived; if that failed, or it arrived
    before this existed, it is fetched now, while Meta still keeps it.
    """
    msg = db.query(WhatsAppMessage).filter(WhatsAppMessage.message_id == message_id).first()
    if msg is None or msg.kind not in inbox.MEDIA_KINDS:
        raise HTTPException(status_code=404, detail="No such file")

    path = (msg.payload or {}).get("stored")
    if not path or not os.path.isfile(path):
        if path:  # held once, since lost: fetch it again
            msg.payload = {k: v for k, v in msg.payload.items() if k != "stored"}
        error = inbox.fetch_media(msg)
        db.commit()
        if error:
            raise HTTPException(status_code=404, detail=f"This file could not be fetched from WhatsApp: {error}")
        path = msg.payload["stored"]

    mime = (msg.payload or {}).get("mime_type") or "application/octet-stream"
    inline = mime in _INLINE_TYPES and not download
    name = (msg.payload or {}).get("filename") or os.path.basename(path)
    return FileResponse(
        path, media_type=mime if inline else "application/octet-stream", filename=name,
        content_disposition_type="inline" if inline else "attachment",
        headers={"X-Content-Type-Options": "nosniff",
                 "Content-Security-Policy": "default-src 'none'; sandbox"},
    )


@router.post("/conversations/{digits}/attention")
def set_attention(digits: str, payload: AttentionRequest, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    """
    Mark a conversation as needing attention, or clear it once answered.

    Only people an AutoGMap campaign reached are marked, by the bot or by
    hand; the number is shared, and other teams' conversations are theirs.
    Clearing is done only here, by a person: the bot never clears it.
    """
    conv = _get_conversation(db, digits)
    if payload.needed:
        if not inbox.from_campaign(db, conv.phone):
            raise HTTPException(status_code=409,
                                detail="Only conversations from an AutoGMap campaign can be marked for attention")
        onboarding_bot.flag(conv, payload.reason or f"Marked by {user.email}")
        ticket = tickets.raise_or_update(db, conv, via=user.email)
    else:
        if payload.disposition and payload.disposition not in handover.DISPOSITIONS:
            raise HTTPException(status_code=400, detail="Unknown disposition")
        conv.needs_attention = False
        conv.attention_resolved_by = user.email
        conv.attention_resolved_at = inbox.now()
        ticket = tickets.resolve(db, conv.phone, user.email)
        if payload.disposition:
            handover.record(db, conv, payload.disposition, user.email, payload.note)
    db.commit()
    return {"needs_attention": conv.needs_attention, "attention_reason": conv.attention_reason,
            "ticket": tickets.as_dict(ticket) if ticket else None}


@router.post("/conversations/{digits}/media", response_model=ThreadMessage)
async def send_media(
    digits: str,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Send a photo, video, audio clip or document from the business number.

    JPEG and PNG go as photos, MP4 and 3GP as videos, AAC, MP3, M4A, AMR and
    OGG as audio; anything else is sent as a document. Like a typed reply,
    only within 24 hours of the person's last message.
    """
    conv = _get_conversation(db, digits)
    if not inbox.window_open(conv):
        raise HTTPException(status_code=409, detail=(
            "The 24-hour reply window has closed. Only an approved template can reach this number now."))

    mime = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    kind = inbox.media_kind(mime)
    limit = inbox.SEND_LIMIT[kind]
    content = await file.read(limit + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The file is empty")
    if len(content) > limit:
        raise HTTPException(status_code=413, detail=(
            f"WhatsApp takes a {kind} of up to {limit // (1024 * 1024)} MB; this file is larger."))

    msg = inbox.send_media(db, conv.phone, content, mime, os.path.basename(file.filename or "file"),
                           (caption or "").strip() or None, sent_by=user.email)
    conv.last_read_at = inbox.now()
    if msg.status != "FAILED":
        handover.take_over(db, conv, user.email)
    db.commit()
    if msg.status == "FAILED":
        raise HTTPException(status_code=502, detail=msg.error_reason)
    return ThreadMessage(
        id=msg.message_id, direction=msg.direction, kind=msg.kind, body=msg.body,
        payload=_public_payload(msg), status=msg.status, sent_by=msg.sent_by,
        created_at=inbox.aware(msg.created_at),
    )
