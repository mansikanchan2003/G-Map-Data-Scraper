"""
The WhatsApp inbox: every conversation with the business number.

Inbound messages arrive through the webhook and are recorded here whatever
they are — a typed message, a quick-reply tap, a photo. Outbound ones are sent
through here too, whether a person typed them in the dashboard or the
onboarding bot sent them, so the thread shows both and says which was which.

Campaign template sends are not copied in. They already live in
whatsapp_campaign_recipients, and the thread reads them from there.
"""
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.models.inbox import WhatsAppConversation, WhatsAppMessage
from src.services.meta_whatsapp_service import MetaWhatsAppService

logger = logging.getLogger("gmap_scraper.inbox")

# Meta accepts a free-form message only within 24 hours of the person's last
# message to us. Anything later needs an approved template.
REPLY_WINDOW = timedelta(hours=24)

# Labels for what cannot be shown as text, so the thread still says something
# arrived rather than showing an empty bubble.
_MEDIA_LABELS = {
    "image": "Photo", "video": "Video", "audio": "Voice message",
    "document": "Document", "sticker": "Sticker",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: Optional[datetime]) -> Optional[datetime]:
    """Read a stored timestamp as UTC. SQLite hands back a naive one."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def normalize_phone(raw: Optional[str]) -> str:
    """
    Meta sends "919876543210"; recipients are stored as "+919876543210".

    One form for both, or a thread could never be joined to the campaigns that
    reached the same number.
    """
    digits = re.sub(r"\D", "", raw or "")
    return f"+{digits}" if digits else ""


def campaign_phones(db: Session, phones: Optional[list] = None) -> set:
    """
    The numbers an AutoGMap campaign has reached.

    The business number is shared with other teams and their own outreach,
    so being in the inbox says nothing about where someone came from. A
    campaign message Meta accepted for the number does.
    """
    from src.models.whatsapp import WhatsAppCampaignRecipient

    query = db.query(WhatsAppCampaignRecipient.phone).filter(
        WhatsAppCampaignRecipient.provider_message_id.isnot(None))
    if phones is not None:
        if not phones:
            return set()
        query = query.filter(WhatsAppCampaignRecipient.phone.in_(phones))
    return {p for (p,) in query.distinct().all()}


def from_campaign(db: Session, phone: str) -> bool:
    return phone in campaign_phones(db, [phone])


def window_expires_at(conv: WhatsAppConversation) -> Optional[datetime]:
    last = aware(conv.last_inbound_at)
    return last + REPLY_WINDOW if last else None


def window_open(conv: WhatsAppConversation) -> bool:
    expires = window_expires_at(conv)
    return bool(expires and now() < expires)


def conversation(db: Session, phone: str, profile_name: Optional[str] = None) -> WhatsAppConversation:
    """The conversation with this number, created on first contact."""
    conv = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == phone).first()
    if conv is None:
        conv = WhatsAppConversation(phone=phone, bot_paused=False)
        db.add(conv)
        db.flush()
    if profile_name:
        conv.profile_name = profile_name[:200]
    return conv


def describe_inbound(message: dict):
    """(kind, body, payload) for one inbound message as Meta sends it."""
    kind = (message.get("type") or "unknown").lower()

    if kind == "text":
        return "text", (message.get("text") or {}).get("body") or "", None

    if kind == "button":
        # A quick-reply button on a template, such as a campaign's.
        button = message.get("button") or {}
        return "button", button.get("text") or "", {"payload": button.get("payload")}

    if kind == "interactive":
        # A reply button or list row on a message we sent outside a template,
        # which is what the onboarding bot sends. The id is what it matches on.
        inter = message.get("interactive") or {}
        reply = inter.get("button_reply") or inter.get("list_reply")
        if reply:
            return "interactive", reply.get("title") or "", {"id": reply.get("id")}
        return "interactive", "[Form reply]", None

    if kind in _MEDIA_LABELS:
        media = message.get(kind) or {}
        caption = media.get("caption") or media.get("filename") or ""
        label = _MEDIA_LABELS[kind]
        return kind, f"[{label}] {caption}".strip(), {
            "media_id": media.get("id"),
            "mime_type": media.get("mime_type"),
            "filename": media.get("filename"),
        }

    if kind == "location":
        loc = message.get("location") or {}
        place = ", ".join(p for p in (loc.get("name"), loc.get("address")) if p)
        return "location", f"[Location] {place}".strip(), {
            "latitude": loc.get("latitude"), "longitude": loc.get("longitude"),
        }

    if kind == "reaction":
        emoji = (message.get("reaction") or {}).get("emoji") or ""
        return "reaction", f"Reacted {emoji}".strip(), None

    if kind == "contacts":
        return "contacts", "[Contact card]", None

    return kind, "[A message type this inbox cannot show]", None


def record_inbound(db: Session, message: dict, profile_name: Optional[str] = None) -> Optional[WhatsAppMessage]:
    """
    Store one inbound message, or nothing if it was already stored.

    Meta redelivers a webhook until it gets a 200, so the same message can
    arrive more than once; its id decides.
    """
    phone = normalize_phone(message.get("from"))
    if not phone:
        return None

    provider_id = message.get("id")
    if provider_id and db.query(WhatsAppMessage.message_id).filter(
        WhatsAppMessage.provider_message_id == provider_id
    ).first():
        return None

    kind, body, payload = describe_inbound(message)
    try:
        at = datetime.fromtimestamp(int(message.get("timestamp")), tz=timezone.utc)
    except (TypeError, ValueError):
        at = now()

    conv = conversation(db, phone, profile_name)
    msg = WhatsAppMessage(
        message_id=uuid.uuid4().hex,
        phone=phone,
        direction="IN",
        kind=kind,
        body=body,
        payload=payload,
        provider_message_id=provider_id,
        context_id=(message.get("context") or {}).get("id"),
        created_at=at,
    )
    db.add(msg)

    # A reaction does not reopen the reply window in Meta's rules, but every
    # other inbound message does.
    if kind != "reaction" and (conv.last_inbound_at is None or aware(conv.last_inbound_at) < at):
        conv.last_inbound_at = at
    if conv.last_message_at is None or aware(conv.last_message_at) < at:
        conv.last_message_at = at
    db.flush()
    return msg


def send(
    db: Session,
    phone: str,
    body: str,
    *,
    sent_by: str,
    buttons: Optional[list] = None,
    link: Optional[dict] = None,
) -> WhatsAppMessage:
    """
    Send a free-form message and record it, sent or not.

    `buttons` ([{"id", "title"}], at most three) makes it a reply-button
    message; `link` ({"text", "url"}) gives it one button that opens a page.
    A refusal by Meta is recorded with its reason rather than dropped: a
    message that silently failed is worse than one visibly marked failed.

    The caller decides whether the 24-hour window allows it.
    """
    meta = MetaWhatsAppService()
    if buttons:
        kind, payload = "buttons", buttons
        ok, provider_id, _s, error, _c = meta.send_button_message(phone, body, buttons)
    elif link:
        kind, payload = "link", link
        ok, provider_id, _s, error, _c = meta.send_link_message(phone, body, link["text"], link["url"])
    else:
        kind, payload = "text", None
        ok, provider_id, _s, error, _c = meta.send_text_message(phone, body)

    conv = conversation(db, phone)
    msg = WhatsAppMessage(
        message_id=uuid.uuid4().hex,
        phone=phone,
        direction="OUT",
        kind=kind,
        body=body,
        payload=payload,
        provider_message_id=provider_id,
        status="SENT" if ok else "FAILED",
        error_reason=None if ok else (error or "Unknown error")[:500],
        sent_by=sent_by,
        created_at=now(),
    )
    db.add(msg)
    conv.last_message_at = msg.created_at
    db.flush()
    if not ok:
        logger.warning(f"inbox event=SEND_FAILED phone=...{phone[-4:]} by={sent_by} reason={msg.error_reason}")
    return msg


MEDIA_DIR = os.environ.get("INBOX_MEDIA_DIR", os.path.join("data", "inbox_media"))
MEDIA_KINDS = tuple(_MEDIA_LABELS)

_EXTENSIONS = {
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif",
    "video/mp4": "mp4", "video/3gpp": "3gp", "audio/ogg": "ogg", "audio/mpeg": "mp3",
    "audio/mp4": "m4a", "audio/aac": "aac", "audio/amr": "amr", "application/pdf": "pdf",
}


# What WhatsApp accepts from us, and as what. Larger documents are allowed by
# Meta, but 16 MB keeps an upload from the dashboard quick and the server light.
SENDABLE = {
    "image/jpeg": "image", "image/png": "image",
    "video/mp4": "video", "video/3gpp": "video",
    "audio/aac": "audio", "audio/mp4": "audio", "audio/mpeg": "audio", "audio/amr": "audio",
    "audio/ogg": "audio",
}
SEND_LIMIT = {"image": 5 * 1024 * 1024, "video": 16 * 1024 * 1024, "audio": 16 * 1024 * 1024,
              "document": 16 * 1024 * 1024}
_LABELS_OUT = {"image": "Photo", "video": "Video", "audio": "Audio", "document": "Document"}


def media_kind(mime: str) -> str:
    """How WhatsApp will show a file of this type: any other type goes as a document."""
    return SENDABLE.get((mime or "").split(";")[0].strip().lower(), "document")


def send_media(db: Session, phone: str, content: bytes, mime: str, filename: str,
               caption: Optional[str], *, sent_by: str) -> WhatsAppMessage:
    """
    Send a file from the inbox and record it, sent or not.

    The file is kept so the thread can show what was sent; Meta is given its
    own copy. The caller checks the 24-hour window and the size.
    """
    kind = media_kind(mime)
    mime = (mime or "application/octet-stream").split(";")[0].strip().lower()
    ext = _EXTENSIONS.get(mime) or (os.path.splitext(filename or "")[1].lstrip(".")[:8]) or "bin"
    ext = re.sub(r"[^A-Za-z0-9]", "", ext) or "bin"
    message_id = uuid.uuid4().hex
    folder = os.path.join(MEDIA_DIR, re.sub(r"\D", "", phone))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{message_id}.{ext}")
    with open(path, "wb") as fh:
        fh.write(content)

    meta = MetaWhatsAppService()
    media_id = meta.upload_media(path, kind)
    if media_id:
        ok, provider_id, _s, error, _c = meta.send_media_message(phone, kind, media_id, caption, filename)
    else:
        ok, provider_id, error = False, None, getattr(meta, "last_media_error", None) or "Could not upload the file to WhatsApp"

    conv = conversation(db, phone)
    label = f"[{_LABELS_OUT[kind]}]"
    msg = WhatsAppMessage(
        message_id=message_id, phone=phone, direction="OUT", kind=kind,
        body=f"{label} {caption or (filename if kind == 'document' else '')}".strip(),
        payload={"stored": path, "mime_type": mime, "filename": filename, "size": len(content)},
        provider_message_id=provider_id,
        status="SENT" if ok else "FAILED",
        error_reason=None if ok else (error or "Unknown error")[:500],
        sent_by=sent_by, created_at=now(),
    )
    db.add(msg)
    conv.last_message_at = msg.created_at
    db.flush()
    return msg


def fetch_media(msg: WhatsAppMessage) -> Optional[str]:
    """
    Download the file an inbound message carries, and note where it was kept.

    Returns the reason when it could not be fetched; that is recorded too, so
    the thread can say so rather than show a broken image.
    """
    payload = dict(msg.payload or {})
    if msg.direction != "IN" or msg.kind not in MEDIA_KINDS or payload.get("stored"):
        return None
    media_id = payload.get("media_id")
    if not media_id:
        return "Meta sent no media id"

    content, mime, error = MetaWhatsAppService().download_media(media_id)
    if content is None:
        msg.payload = {**payload, "fetch_error": (error or "Unknown error")[:300]}
        return error

    mime = (mime or payload.get("mime_type") or "application/octet-stream").split(";")[0].strip()
    name = payload.get("filename") or ""
    ext = _EXTENSIONS.get(mime) or (os.path.splitext(name)[1].lstrip(".")[:8] if name else "") or "bin"
    folder = os.path.join(MEDIA_DIR, re.sub(r"\D", "", msg.phone))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{msg.message_id}.{re.sub(r'[^A-Za-z0-9]', '', ext) or 'bin'}")
    with open(path, "wb") as fh:
        fh.write(content)
    msg.payload = {**{k: v for k, v in payload.items() if k != "fetch_error"},
                   "stored": path, "mime_type": mime, "size": len(content)}
    return None


def fetch_media_in_background(message_ids: list) -> None:
    """Runs after the webhook has answered, in its own session."""
    from src.database import SessionLocal

    db = SessionLocal()
    try:
        for message_id in message_ids:
            msg = db.query(WhatsAppMessage).filter(WhatsAppMessage.message_id == message_id).first()
            if msg is None or msg.kind not in MEDIA_KINDS:
                continue
            try:
                error = fetch_media(msg)
                db.commit()
                if error:
                    logger.warning(f"inbox event=MEDIA_NOT_FETCHED message_id={message_id} reason={error}")
            except Exception:
                db.rollback()
                logger.exception(f"inbox event=MEDIA_FETCH_FAILED message_id={message_id}")
    finally:
        db.close()


# How far along each outbound stage sits, so a late "delivered" cannot
# overwrite a "read".
_RANK = {"SENT": 1, "DELIVERED": 2, "READ": 3}


def apply_status(db: Session, status: dict) -> bool:
    """Move an inbox message's ticks forward. False if it is not an inbox message."""
    provider_id = status.get("id")
    stage = (status.get("status") or "").upper()
    if not provider_id or not stage:
        return False
    msg = db.query(WhatsAppMessage).filter(WhatsAppMessage.provider_message_id == provider_id).first()
    if msg is None or msg.direction != "OUT":
        return False

    if stage == "FAILED":
        msg.status = "FAILED"
        errors = status.get("errors") or []
        if errors:
            err = errors[0]
            details = (err.get("error_data") or {}).get("details") or ""
            msg.error_reason = f"[{err.get('code')}] {err.get('title', '')} {details}".strip()[:500]
    elif stage in _RANK and msg.status != "FAILED" and _RANK[stage] > _RANK.get(msg.status or "", 0):
        msg.status = stage
    return True


def backfill_from_leads(db: Session) -> int:
    """
    Copy quick-reply taps and typed replies recorded before the inbox existed.

    Each copy keeps the id of the row it came from, so running this again
    copies nothing twice. Returns how many messages were added.
    """
    from src.models.whatsapp import WhatsAppButtonClick, WhatsAppCampaignRecipient, WhatsAppReply

    existing = {m for (m,) in db.query(WhatsAppMessage.message_id).all()}
    # A tap the live webhook has already recorded is in the inbox under its
    # own id; it is recognised by Meta's id instead.
    seen_provider = {p for (p,) in db.query(WhatsAppMessage.provider_message_id)
                     .filter(WhatsAppMessage.provider_message_id.isnot(None)).all()}
    added = 0

    taps = (
        db.query(WhatsAppButtonClick, WhatsAppCampaignRecipient)
        .join(WhatsAppCampaignRecipient,
              WhatsAppCampaignRecipient.recipient_id == WhatsAppButtonClick.recipient_id)
        .all()
    )
    for click, recipient in taps:
        if click.click_id in existing or not recipient.phone or (
                click.provider_message_id and click.provider_message_id in seen_provider):
            continue
        conv = conversation(db, recipient.phone)
        at = aware(click.clicked_at)
        db.add(WhatsAppMessage(
            message_id=click.click_id, phone=recipient.phone, direction="IN",
            kind="button", body=click.button_text or "",
            payload={"payload": click.button_payload},
            # Carried over so a late redelivery of this tap is recognised.
            provider_message_id=click.provider_message_id,
            context_id=recipient.provider_message_id, created_at=at,
        ))
        if conv.last_inbound_at is None or aware(conv.last_inbound_at) < at:
            conv.last_inbound_at = at
        if conv.last_message_at is None or aware(conv.last_message_at) < at:
            conv.last_message_at = at
        added += 1

    for reply in db.query(WhatsAppReply).all():
        if reply.reply_id in existing or (
                reply.provider_message_id and reply.provider_message_id in seen_provider):
            continue
        conv = conversation(db, reply.phone)
        at = aware(reply.sent_at)
        db.add(WhatsAppMessage(
            message_id=reply.reply_id, phone=reply.phone, direction="OUT",
            kind="text", body=reply.body, status=reply.status,
            provider_message_id=reply.provider_message_id,
            error_reason=reply.error_reason, sent_by=reply.sent_by, created_at=at,
        ))
        if conv.last_message_at is None or aware(conv.last_message_at) < at:
            conv.last_message_at = at
        added += 1

    if added:
        db.commit()
        logger.info(f"inbox event=BACKFILLED messages={added}")
    return added
