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
    added = 0

    taps = (
        db.query(WhatsAppButtonClick, WhatsAppCampaignRecipient)
        .join(WhatsAppCampaignRecipient,
              WhatsAppCampaignRecipient.recipient_id == WhatsAppButtonClick.recipient_id)
        .all()
    )
    for click, recipient in taps:
        if click.click_id in existing or not recipient.phone:
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
        if reply.reply_id in existing:
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
