"""
The onboarding bot: what happens after someone taps "Interested" on a campaign.

    tap "Interested"      -> ask for their PIN code
    PIN within our area   -> "Can you invest 5 lakh?"            [Yes] [No]
    Yes                   -> the documents needed, "Have them?"   [Yes] [No]
    Yes                   -> a link to the upload page
    documents submitted   -> "Thank you, our team will reach out"

Each conversation remembers the step it is on (WhatsAppConversation.bot_step),
because the same reply means different things at different steps. The bot
stays quiet when it is switched off, when someone has paused it for that
conversation to answer by hand, and for anything it was not waiting for —
those are left for a person in the inbox.

Every message it sends answers one the person just sent, so all of them fall
inside Meta's 24-hour window and none needs a template.
"""
import json
import logging
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.models.app_setting import AppSetting
from src.models.inbox import WhatsAppConversation, WhatsAppMessage
from src.services import inbox, pincode_coverage

logger = logging.getLogger("gmap_scraper.onboarding_bot")

SETTINGS_KEY = "onboarding_bot"
DEFAULT_SETTINGS = {
    "enabled": True,
    # Quick-reply buttons on a campaign that start the bot. Matched without
    # regard to case, spaces or punctuation, so "Interested?" matches too.
    "triggers": ["Interested"],
}

# Steps. Anything not in WAITING is an end state: the bot says nothing more
# until the person taps a trigger button again.
AWAIT_PIN = "AWAIT_PIN"
AWAIT_INVEST = "AWAIT_INVEST"
AWAIT_DOCS = "AWAIT_DOCS"
AWAIT_UPLOAD = "AWAIT_UPLOAD"
SUBMITTED = "SUBMITTED"
NOT_SERVED = "NOT_SERVED"
NOT_INVESTING = "NOT_INVESTING"
HANDOVER = "HANDOVER"

STEP_LABELS = {
    AWAIT_PIN: "Waiting for PIN code",
    AWAIT_INVEST: "Asked about investment",
    AWAIT_DOCS: "Asked about documents",
    AWAIT_UPLOAD: "Upload link sent",
    SUBMITTED: "Documents submitted",
    NOT_SERVED: "Outside our area",
    NOT_INVESTING: "Cannot invest",
    HANDOVER: "Needs a person",
}

# The documents asked for on the upload page and listed in the chat, in the
# order SBI's CSP onboarding lists them. The required ones must be uploaded
# before the page can be submitted; the rest are uploaded if the person has
# them. Keys are kept for documents that existed before, so files already
# uploaded keep their names.
DOCUMENTS = [
    {"key": "pan", "label": "PAN Card (Self Attested)", "hint": None, "required": True},
    {"key": "aadhaar", "label": "Aadhaar Card (Self Attested)", "hint": "Front and back, in one file", "required": True},
    {"key": "photo", "label": "Passport Size Photo", "hint": None, "required": True},
    {"key": "cibil", "label": "Full CIBIL Report", "hint": None, "required": False},
    {"key": "police", "label": "Police Verification Certificate (valid) / Application Receipt (Self Attested)",
     "hint": None, "required": False},
    {"key": "voter_dl", "label": "Voter Card / Driving Licence", "hint": None, "required": False},
    {"key": "iibf", "label": "IIBF Certificate (if available)", "hint": None, "required": False},
    {"key": "edu_12", "label": "Education Certificate — Class XII (Self Attested)", "hint": None, "required": False},
    {"key": "bank", "label": "SBI Savings/Current Account Statement or Passbook copy (Self Attested)",
     "hint": None, "required": False},
    {"key": "edu_higher", "label": "Education Certificate — Above Class XII (Self Attested)",
     "hint": None, "required": False},
]
REQUIRED_DOCUMENTS = [d for d in DOCUMENTS if d["required"]]

# A PIN asked for this many times without a usable answer goes to a person.
MAX_PIN_ATTEMPTS = 3
UPLOAD_LINK_DAYS = 7

YES_WORDS = {"yes", "y", "yeah", "yep", "ok", "okay", "haan", "han", "ha", "haa", "ji", "hanji", "haanji"}
NO_WORDS = {"no", "n", "nope", "nahi", "nahin", "na", "nhi"}

# --- What the bot says ------------------------------------------------------

ASK_PIN = "Thank you for your interest! 🙏\n\nPlease provide your PIN code."
BAD_PIN = "Please send your 6-digit PIN code, for example 110001."
UNKNOWN_PIN = "We couldn't find the PIN code {pin}. Please check it and send it again."
HANDOVER_TEXT = "Thank you! One of our team members will contact you shortly to help you further."
NOT_SERVED_TEXT = (
    "Thank you for sharing your PIN code. We are not available near {pin} yet, "
    "but we are expanding fast and will reach out to you as soon as we are.\n\n"
    "If you'd like to check another PIN code, just send it here."
)
ASK_INVEST = "Are you someone who can invest ₹5 Lakh for the business startup?"
NOT_INVESTING_TEXT = (
    "Thank you for letting us know. If anything changes, just reply here and "
    "our team will be happy to help."
)
ASK_DOCS = (
    "Great! Please let me know if you have these documents needed for your "
    "onboarding with us, with you?\n\n{documents}"
)
DOCS_LATER = (
    "No problem. Once you have these documents ready, tap *Yes* above and "
    "we'll send you the link to upload them."
)
SEND_LINK = (
    "Great! Let's get you registered with us. 📝\n\n"
    "Please upload the mentioned documents on this link."
)
LINK_BUTTON = "Upload documents"
THANKS = (
    "Thank you for sharing your documents, one of our team members will "
    "reach out to you shortly."
)
ALREADY_SUBMITTED = (
    "We have already received your documents, thank you! One of our team "
    "members will reach out to you shortly."
)

# Answers to messages the bot was not waiting for. Someone who writes should
# never be met with silence, but nor should they get the same line back
# every time they type, so these are paced (see _fallback).
GREETING = (
    "Hello! 👋 Thank you for contacting Eko.\n\n"
    "Would you like to start your own business as an SBI Customer Service "
    "Point, with Eko? Tap *Interested* to get started."
)
START_BUTTON = [{"id": "start:interested", "title": "Interested"}]
REMIND_PIN = "Please send your 6-digit PIN code, for example 110001."
REMIND_INVEST = "Please tap *Yes* or *No* below.\n\n" + ASK_INVEST
REMIND_DOCS = "Please tap *Yes* or *No* below.\n\n" + ASK_DOCS
REMIND_UPLOAD = "You can upload your documents on this link whenever you're ready."
NOT_SERVED_AGAIN = (
    "We are not available near {pin} yet. If you'd like to check another "
    "PIN code, just send it here."
)
ACKNOWLEDGE = (
    "Thank you for your message! One of our team members will get back to "
    "you shortly."
)

# Not more than one such answer in this long, per conversation...
FALLBACK_GAP = timedelta(minutes=5)
# ...the greeting to someone who never started not more than once a day...
GREETING_GAP = timedelta(hours=24)
# ...and none at all after this many in a row that the bot did not
# understand. Many businesses have an auto-reply, and two automatic
# responders answering each other would never stop on their own.
MAX_FALLBACK_STREAK = 3

YES_NO = lambda prefix: [  # noqa: E731
    {"id": f"{prefix}:yes", "title": "Yes"},
    {"id": f"{prefix}:no", "title": "No"},
]


def document_list() -> str:
    """The documents as the chat lists them: the required ones first, then the rest."""
    required = [d for d in DOCUMENTS if d["required"]]
    optional = [d for d in DOCUMENTS if not d["required"]]
    lines = ["*Required:*"] + [f"{i}. {d['label']}" for i, d in enumerate(required, start=1)]
    if optional:
        lines += ["", "*Also needed, if you have them:*"]
        lines += [f"{i}. {d['label']}" for i, d in enumerate(optional, start=len(required) + 1)]
    return "\n".join(lines)


# --- Settings ---------------------------------------------------------------

def get_settings(db: Session) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == SETTINGS_KEY).first()
    stored = {}
    if row and row.value:
        try:
            stored = json.loads(row.value)
        except ValueError:
            logger.warning("onboarding_bot event=BAD_SETTINGS using defaults")
    return {**DEFAULT_SETTINGS, **stored}


def save_settings(db: Session, enabled: bool, triggers: list) -> dict:
    cleaned = []
    for t in triggers:
        t = (t or "").strip()
        if t and t not in cleaned:
            cleaned.append(t[:25])
    value = {"enabled": bool(enabled), "triggers": cleaned}
    row = db.query(AppSetting).filter(AppSetting.key == SETTINGS_KEY).first()
    if row is None:
        db.add(AppSetting(key=SETTINGS_KEY, value=json.dumps(value)))
    else:
        row.value = json.dumps(value)
    db.commit()
    return value


def _norm(text: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def is_trigger(text: Optional[str], triggers: list) -> bool:
    key = _norm(text)
    return bool(key) and any(key == _norm(t) for t in triggers)


# --- The flow ---------------------------------------------------------------

def public_base_url() -> str:
    return (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/") or "http://localhost:8000"


def upload_url(conv: WhatsAppConversation) -> str:
    return f"{public_base_url()}/onboard/{conv.upload_token}"


def _say(db, conv, body, **kw) -> WhatsAppMessage:
    return inbox.send(db, conv.phone, body, sent_by="bot", **kw)


def _move(conv, step, **data):
    conv.bot_step = step
    conv.bot_data = {**(conv.bot_data or {}), **data}
    conv.bot_updated_at = inbox.now()


def _answer(msg: WhatsAppMessage, prefix: str) -> Optional[bool]:
    """True for yes, False for no, None for neither — by button id, or typed."""
    if msg.kind == "interactive":
        tapped = (msg.payload or {}).get("id") or ""
        if tapped == f"{prefix}:yes":
            return True
        if tapped == f"{prefix}:no":
            return False
        return None
    if msg.kind == "text":
        word = _norm(msg.body)
        if word in YES_WORDS:
            return True
        if word in NO_WORDS:
            return False
    return None


def _send_upload_link(db, conv):
    """Send the upload link, issuing a fresh one if there is none or it lapsed."""
    expires = inbox.aware(conv.upload_token_expires_at)
    if not conv.upload_token or not expires or expires <= inbox.now():
        conv.upload_token = secrets.token_urlsafe(24)
        conv.upload_token_expires_at = inbox.now() + timedelta(days=UPLOAD_LINK_DAYS)
    _move(conv, AWAIT_UPLOAD)
    _say(db, conv, SEND_LINK, link={"text": LINK_BUTTON, "url": upload_url(conv)})


def _pin_failed(db, conv, reply: str):
    attempts = (conv.bot_data or {}).get("pin_attempts", 0) + 1
    if attempts >= MAX_PIN_ATTEMPTS:
        _move(conv, HANDOVER, pin_attempts=attempts)
        _say(db, conv, HANDOVER_TEXT)
    else:
        _move(conv, AWAIT_PIN, pin_attempts=attempts)
        _say(db, conv, reply)


def _on_pin(db, conv, msg):
    pin = pincode_coverage.extract_pincode(msg.body) if msg.kind == "text" else None
    if not pin:
        _pin_failed(db, conv, BAD_PIN)
        return

    result = pincode_coverage.check(db, pin)
    logger.info(f"onboarding_bot event=PIN_CHECKED pin={pin} result={result['status']} "
                f"km={result.get('distance_km')}")
    if result["status"] == "unknown":
        _pin_failed(db, conv, UNKNOWN_PIN.format(pin=pin))
        return

    coverage = {k: result.get(k) for k in ("pincode", "nearest_pincode", "distance_km", "place")}
    if result["status"] == "served":
        _move(conv, AWAIT_INVEST, coverage=coverage)
        _say(db, conv, ASK_INVEST, buttons=YES_NO("invest"))
    else:
        _move(conv, NOT_SERVED, coverage=coverage)
        _say(db, conv, NOT_SERVED_TEXT.format(pin=pin))


def _only_a_pin(msg: WhatsAppMessage) -> Optional[str]:
    """A PIN when the message is nothing but one; "500000" mid-sentence may be an amount."""
    body = re.sub(r"[\s-]", "", msg.body or "")
    return body if msg.kind == "text" and re.fullmatch(r"[1-9]\d{5}", body) else None


def _start(db, conv, msg):
    if conv.documents_submitted_at:
        _say(db, conv, ALREADY_SUBMITTED)
        return
    # Tapping the button again starts over: whatever was said before, this
    # is the person asking again.
    conv.bot_data = {}
    _move(conv, AWAIT_PIN, pin_attempts=0, trigger=msg.body)
    _say(db, conv, ASK_PIN)


def _fallback(db, conv, body, gap=FALLBACK_GAP, **kw):
    """
    Answer a message the bot did not understand, if it has not just done so.

    Paced, and stopped after a few in a row, so that a person typing several
    lines gets one answer and an auto-reply cannot start an endless exchange.
    """
    data = conv.bot_data or {}
    streak = data.get("fallback_streak", 0)
    last = data.get("fallback_at")
    if streak >= MAX_FALLBACK_STREAK:
        return
    if last and inbox.now() - datetime.fromisoformat(last) < gap:
        return
    conv.bot_data = {**data, "fallback_streak": streak + 1, "fallback_at": inbox.now().isoformat()}
    _say(db, conv, body, **kw)


def _understood(conv):
    """The person said something the bot could act on; any pacing starts afresh."""
    data = conv.bot_data or {}
    if data.get("fallback_streak") or data.get("fallback_at"):
        conv.bot_data = {k: v for k, v in data.items() if k not in ("fallback_streak", "fallback_at")}


def handle(db: Session, conv: WhatsAppConversation, msg: WhatsAppMessage) -> None:
    """Answer one inbound message. Every message gets a fitting reply, paced."""
    if msg.direction != "IN" or conv.bot_paused:
        return
    cfg = get_settings(db)
    if not cfg["enabled"]:
        return
    # The number is shared with other teams, who talk to people of their
    # own. The bot speaks only to people an AutoGMap campaign reached; every
    # other conversation is still shown in the inbox, and left to a person.
    if not inbox.from_campaign(db, conv.phone):
        return
    # A reaction is not a message to answer.
    if msg.kind == "reaction":
        return

    tapped = (msg.payload or {}).get("id") if msg.kind == "interactive" else None
    if (msg.kind == "button" and is_trigger(msg.body, cfg["triggers"])) or tapped == START_BUTTON[0]["id"]:
        _understood(conv)
        _start(db, conv, msg)
        return

    step = conv.bot_step

    # A PIN code is checked whenever one is sent, not only when asked for:
    # someone told "not in your area" may well try another. Mid-question
    # only a message that is nothing but a PIN counts, so "yes, 500000"
    # is not read as one; once the upload link is out, the PIN is settled.
    if step not in (AWAIT_UPLOAD, SUBMITTED):
        pin = (_only_a_pin(msg) if step in (AWAIT_INVEST, AWAIT_DOCS)
               else pincode_coverage.extract_pincode(msg.body) if msg.kind == "text" else None)
        if pin:
            _understood(conv)
            _on_pin(db, conv, msg)
            return

    if step == AWAIT_PIN:
        # _on_pin counts the failed attempts and hands over after a few.
        if msg.kind == "text":
            _on_pin(db, conv, msg)
        else:
            _fallback(db, conv, REMIND_PIN)

    elif step == AWAIT_INVEST:
        answer = _answer(msg, "invest")
        if answer is True:
            _understood(conv)
            _move(conv, AWAIT_DOCS, can_invest=True)
            _say(db, conv, ASK_DOCS.format(documents=document_list()), buttons=YES_NO("docs"))
        elif answer is False:
            _understood(conv)
            _move(conv, NOT_INVESTING, can_invest=False)
            _say(db, conv, NOT_INVESTING_TEXT)
        else:
            _fallback(db, conv, REMIND_INVEST, buttons=YES_NO("invest"))

    elif step in (AWAIT_DOCS, AWAIT_UPLOAD):
        # At AWAIT_UPLOAD a second "Yes" means the link was lost; send it again.
        answer = _answer(msg, "docs")
        if answer is True:
            _understood(conv)
            _send_upload_link(db, conv)
        elif answer is False and step == AWAIT_DOCS:
            _understood(conv)
            _move(conv, AWAIT_DOCS, has_documents=False)
            _say(db, conv, DOCS_LATER)
        elif step == AWAIT_DOCS:
            _fallback(db, conv, REMIND_DOCS.format(documents=document_list()), buttons=YES_NO("docs"))
        else:
            _fallback(db, conv, REMIND_UPLOAD, link={"text": LINK_BUTTON, "url": upload_url(conv)})

    elif step == SUBMITTED:
        _fallback(db, conv, ALREADY_SUBMITTED)

    elif step == NOT_SERVED:
        pin = ((conv.bot_data or {}).get("coverage") or {}).get("pincode") or "your area"
        _fallback(db, conv, NOT_SERVED_AGAIN.format(pin=pin))

    elif step in (NOT_INVESTING, HANDOVER):
        _fallback(db, conv, ACKNOWLEDGE)

    else:
        # Never started: someone writing to the number of their own accord,
        # or answering a campaign with a button other than the trigger.
        if msg.kind == "button":
            _fallback(db, conv, ACKNOWLEDGE)
        else:
            _fallback(db, conv, GREETING, gap=GREETING_GAP, buttons=START_BUTTON)


def documents_submitted(db: Session, conv: WhatsAppConversation) -> WhatsAppMessage:
    """The upload page was submitted: thank the person in the chat."""
    conv.documents_submitted_at = inbox.now()
    _move(conv, SUBMITTED)
    return _say(db, conv, THANKS)


def run(message_ids: list) -> None:
    """
    Answer newly recorded inbound messages. Runs after the webhook has replied.

    In its own session, because the request's is closed by then, and outside
    the request because each answer is a call to Meta: a slow one must not
    delay the 200 Meta waits for, or it redelivers the event.
    """
    from src.database import SessionLocal

    db = SessionLocal()
    try:
        for message_id in message_ids:
            msg = db.query(WhatsAppMessage).filter(WhatsAppMessage.message_id == message_id).first()
            if msg is None:
                continue
            conv = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == msg.phone).first()
            try:
                handle(db, conv, msg)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(f"onboarding_bot event=HANDLE_FAILED message_id={message_id}")
    finally:
        db.close()
