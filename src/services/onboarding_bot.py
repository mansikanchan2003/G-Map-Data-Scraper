"""
The onboarding bot: what happens after someone taps a campaign's buttons.

    tap "Interested"        -> choose a language: English / Hindi / theirs
      language chosen       -> ask for their PIN code
      PIN within our area   -> "How far have you studied?"
                                 [12th/Diploma] [Graduate/Post-Grad] [Other]
      Other                 -> "Sorry, at least 12th or a Diploma is needed" (ends)
      12th or Graduate      -> "Do you have a franchise background?" [Yes] [No]
      either answer         -> "Can you invest 5 lakh?"            [Yes] [No]
      Yes                   -> the documents needed, "Have them?"   [Yes] [No]
      Yes                   -> a link to the upload page
      documents submitted   -> "Thank you, our team will reach out"

    tap "Webinar Chahiye"   -> choose a language
      language chosen       -> "Available for the webinar tomorrow?" [Yes] [No]
      Yes                   -> "Our team will send the link and timing"
      No                    -> "When would suit you?" -> noted, team told

The webinar button is written in the campaign's own language, so every
version of it is recognised (campaign_buttons). Once a language is chosen the
bot speaks only that language (bot_messages), and it is remembered, so the
second flow does not ask again.

Each conversation remembers the step it is on (WhatsAppConversation.bot_step),
because the same reply means different things at different steps. The bot
speaks only to people an AutoGMap campaign reached, stays quiet when switched
off or paused for a conversation, and answers anything it did not expect with
a short, paced reply.

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
from src.services import bot_messages, campaign_buttons, inbox, pincode_coverage
from src.services.bot_messages import LANGUAGE_NAMES, LANGUAGE_WORDS, MESSAGES

logger = logging.getLogger("gmap_scraper.onboarding_bot")

SETTINGS_KEY = "onboarding_bot"
DEFAULT_SETTINGS = {
    "enabled": True,
    # Quick-reply buttons on a campaign that start onboarding. Matched without
    # regard to case, spaces or punctuation, so "Interested?" matches too.
    # The webinar button is fixed per language; see campaign_buttons.
    "triggers": [campaign_buttons.INTERESTED],
}

# Steps.
CHOOSE_LANG = "CHOOSE_LANG"
AWAIT_PIN = "AWAIT_PIN"
AWAIT_EDUCATION = "AWAIT_EDUCATION"
AWAIT_FRANCHISE = "AWAIT_FRANCHISE"
NOT_ELIGIBLE = "NOT_ELIGIBLE"
AWAIT_INVEST = "AWAIT_INVEST"
AWAIT_DOCS = "AWAIT_DOCS"
AWAIT_UPLOAD = "AWAIT_UPLOAD"
SUBMITTED = "SUBMITTED"
NOT_SERVED = "NOT_SERVED"
NOT_INVESTING = "NOT_INVESTING"
HANDOVER = "HANDOVER"
AWAIT_WEBINAR = "AWAIT_WEBINAR"
AWAIT_AVAILABILITY = "AWAIT_AVAILABILITY"
WEBINAR_CONFIRMED = "WEBINAR_CONFIRMED"
WEBINAR_AVAILABILITY = "WEBINAR_AVAILABILITY"

STEP_LABELS = {
    CHOOSE_LANG: "Choosing a language",
    AWAIT_PIN: "Waiting for PIN code",
    AWAIT_EDUCATION: "Asked about education",
    AWAIT_FRANCHISE: "Asked about franchise",
    NOT_ELIGIBLE: "Below 12th — not eligible",
    AWAIT_INVEST: "Asked about investment",
    AWAIT_DOCS: "Asked about documents",
    AWAIT_UPLOAD: "Upload link sent",
    SUBMITTED: "Documents submitted",
    NOT_SERVED: "Outside our area",
    NOT_INVESTING: "Cannot invest",
    HANDOVER: "Needs a person",
    AWAIT_WEBINAR: "Asked about webinar",
    AWAIT_AVAILABILITY: "Asked webinar availability",
    WEBINAR_CONFIRMED: "Webinar confirmed",
    WEBINAR_AVAILABILITY: "Webinar time shared",
}

# Which flow a language choice leads into.
ONBOARD = "onboard"
WEBINAR = "webinar"

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

# Typed answers taken as yes or no, in every language the bot speaks, as
# well as the ways people write them in Latin letters.
_YES_TYPED = {"yes", "y", "yeah", "yep", "ok", "okay", "haan", "han", "ha", "haa", "ji", "hanji", "haanji", "ho"}
_NO_TYPED = {"no", "n", "nope", "nahi", "nahin", "na", "nhi", "nai"}
YES_WORDS = _YES_TYPED | {campaign_buttons.key(m["yes"]) for m in MESSAGES.values()}
NO_WORDS = _NO_TYPED | {campaign_buttons.key(m["no"]) for m in MESSAGES.values()}

# English texts, kept by name for code and tests that read them directly.
_EN = MESSAGES["en"]
ASK_PIN = _EN["ask_pin"]
BAD_PIN = _EN["bad_pin"]
UNKNOWN_PIN = _EN["unknown_pin"]
HANDOVER_TEXT = _EN["handover"]
NOT_SERVED_TEXT = _EN["not_served"]
NOT_SERVED_AGAIN = _EN["not_served_again"]
ASK_INVEST = _EN["ask_invest"]
NOT_INVESTING_TEXT = _EN["not_investing"]
ASK_DOCS = _EN["ask_docs"]
DOCS_LATER = _EN["docs_later"]
SEND_LINK = _EN["send_link"]
LINK_BUTTON = _EN["link_button"]
THANKS = _EN["thanks"]
ALREADY_SUBMITTED = _EN["already_submitted"]
ACKNOWLEDGE = _EN["acknowledge"]
REMIND_PIN = _EN["bad_pin"]
REMIND_INVEST = _EN["remind_choice"] + "\n\n" + ASK_INVEST
REMIND_DOCS = _EN["remind_choice"] + "\n\n" + ASK_DOCS
REMIND_UPLOAD = _EN["remind_upload"]
WEBINAR_ASK = _EN["webinar_ask"]
WEBINAR_YES = _EN["webinar_yes"]
WEBINAR_NO = _EN["webinar_no"]
WEBINAR_NOTED = _EN["webinar_noted"]
ASK_EDUCATION = _EN["ask_education"]
NOT_ELIGIBLE_TEXT = _EN["not_eligible"]
ASK_FRANCHISE = _EN["ask_franchise"]

# The education answers. Only 12th/Diploma and above can open an SBI CSP;
# "other" ends the conversation with a polite no.
EDUCATION_LEVELS = ("12", "grad", "other")
_EDU_KEYS = {"12": "edu_12", "grad": "edu_grad", "other": "edu_other"}
# Typed rather than tapped. Checked after the button labels themselves.
_EDU_TYPED = {
    "12": {"12", "12th", "12thpass", "diploma", "intermediate", "inter", "hsc", "12vi"},
    "grad": {"graduate", "graduation", "postgraduate", "pg", "ba", "bsc", "bcom", "ma", "msc", "mcom",
             "mba", "btech", "degree", "graduatepostgrad"},
    "other": {"other", "10th", "10", "below12", "none"},
}

START_INTERESTED = "start:interested"
START_WEBINAR = "start:webinar"

# Not more than one unexpected-message reply in this long, per conversation...
FALLBACK_GAP = timedelta(minutes=5)
# ...the greeting to someone who never started not more than once a day...
GREETING_GAP = timedelta(hours=24)
# ...and none at all after this many in a row that the bot did not
# understand. Many businesses have an auto-reply, and two automatic
# responders answering each other would never stop on their own.
MAX_FALLBACK_STREAK = 3

# Kept across a restart of either flow: what the person already told us.
_REMEMBERED = ("lang", "lang_campaign", "campaign_lang", "webinar")


def YES_NO(prefix: str, lang: str = "en") -> list:
    return [
        {"id": f"{prefix}:yes", "title": bot_messages.text(lang, "yes")},
        {"id": f"{prefix}:no", "title": bot_messages.text(lang, "no")},
    ]


def document_list(lang: str = "en") -> str:
    """The documents as the chat lists them: the required ones first, then the rest."""
    required = [d for d in DOCUMENTS if d["required"]]
    optional = [d for d in DOCUMENTS if not d["required"]]
    lines = [f"*{bot_messages.text(lang, 'docs_required')}*"]
    lines += [f"{i}. {d['label']}" for i, d in enumerate(required, start=1)]
    if optional:
        lines += ["", f"*{bot_messages.text(lang, 'docs_optional')}*"]
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


def is_trigger(text: Optional[str], triggers: list) -> bool:
    key = campaign_buttons.key(text)
    return bool(key) and any(key == campaign_buttons.key(t) for t in triggers)


# --- Language ---------------------------------------------------------------

# The script each regional language is written in, to tell from a campaign's
# text which language it went out in. Odia templates are registered at Meta
# as en_US, so the registered code alone cannot say.
_SCRIPTS = [
    ("pa", "਀", "੿"), ("gu", "઀", "૿"), ("bn", "ঀ", "৿"),
    ("or", "଀", "୿"), ("ta", "஀", "௿"), ("te", "ఀ", "౿"),
    ("kn", "ಀ", "೿"), ("ml", "ഀ", "ൿ"), ("hi", "ऀ", "ॿ"),
]


def language_of_template(template) -> str:
    """The language a campaign's template was written in; English if unknown."""
    if template is None:
        return "en"
    code = (template.language_code or "").split("_")[0].lower()
    # A regional code says it outright. Only en/en_US needs the text read,
    # because that is what Odia, and the team's early Hindi, were registered as.
    if code in MESSAGES and code != "en":
        return code
    # The script most of the text is in. Not any letter at all: a Gujarati
    # template with one stray Punjabi letter in it was taken for Punjabi.
    body = template.body or ""
    counts = {lang: sum(1 for ch in body if lo <= ch <= hi) for lang, lo, hi in _SCRIPTS}
    lang, n = max(counts.items(), key=lambda kv: kv[1])
    if n >= 5:
        return lang
    return code if code in MESSAGES else "en"


def campaign_language(db: Session, phone: str) -> str:
    """The language of the most recent campaign this number was sent."""
    from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient

    # The newest campaign whose template still exists: a deleted template
    # leaves its campaigns without one, and says nothing about the language.
    row = (db.query(WhatsAppCampaign)
           .join(WhatsAppCampaignRecipient,
                 WhatsAppCampaignRecipient.campaign_id == WhatsAppCampaign.campaign_id)
           .filter(WhatsAppCampaignRecipient.phone == phone,
                   WhatsAppCampaignRecipient.provider_message_id.isnot(None),
                   WhatsAppCampaign.template_id.isnot(None))
           .order_by(WhatsAppCampaignRecipient.created_at.desc())
           .first())
    return language_of_template(row.template if row else None)


def _campaign_lang(db, conv) -> str:
    """
    The language of the newest campaign this person was sent.

    Read afresh rather than kept: a Gujarati campaign sent after an English
    one must be answered as Gujarati, not as whatever was true earlier.
    """
    lang = campaign_language(db, conv.phone)
    if (conv.bot_data or {}).get("campaign_lang") != lang:
        conv.bot_data = {**(conv.bot_data or {}), "campaign_lang": lang}
    return lang


def _chosen_lang(db, conv) -> Optional[str]:
    """
    The language the person chose, while it still applies.

    A choice is made between English, Hindi and the language of the campaign
    in front of them. Once a campaign in another language arrives, that
    choice no longer covers it, and they are asked again.
    """
    data = conv.bot_data or {}
    if data.get("lang") and data.get("lang_campaign") == _campaign_lang(db, conv):
        return data["lang"]
    return None


def _lang(db, conv) -> str:
    """The language to answer in: the one chosen, else the campaign's."""
    return _chosen_lang(db, conv) or _campaign_lang(db, conv)


def language_options(campaign_lang: str) -> list:
    """English, Hindi, and the campaign's own language when it is another."""
    options = ["en", "hi"]
    if campaign_lang not in options and campaign_lang in MESSAGES:
        options.append(campaign_lang)
    return options


def _language_answer(msg: WhatsAppMessage) -> Optional[str]:
    """The language chosen, by button or typed; None if this is not a choice."""
    if msg.kind == "interactive":
        tapped = (msg.payload or {}).get("id") or ""
        code = tapped.split(":", 1)[1] if tapped.startswith("lang:") else None
        return code if code in MESSAGES else None
    if msg.kind == "text":
        typed = campaign_buttons.key(msg.body)
        for code in MESSAGES:
            if typed == campaign_buttons.key(LANGUAGE_NAMES[code]) or typed in LANGUAGE_WORDS.get(code, []):
                return code
    return None


# --- The flow ---------------------------------------------------------------

def public_base_url() -> str:
    return (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/") or "http://localhost:8000"


def upload_url(conv: WhatsAppConversation) -> str:
    return f"{public_base_url()}/onboard/{conv.upload_token}"


def _say(db, conv, body, **kw) -> WhatsAppMessage:
    return inbox.send(db, conv.phone, body, sent_by="bot", **kw)


def _t(db, conv, key, **fields) -> str:
    return bot_messages.text(_lang(db, conv), key, **fields)


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
        word = campaign_buttons.key(msg.body)
        if word in YES_WORDS:
            return True
        if word in NO_WORDS:
            return False
    return None


def education_buttons(lang: str) -> list:
    return [{"id": f"edu:{level}", "title": bot_messages.text(lang, _EDU_KEYS[level])}
            for level in EDUCATION_LEVELS]


def _education_answer(msg: WhatsAppMessage) -> Optional[str]:
    """12, grad or other, by button or typed; None if this is not an answer."""
    if msg.kind == "interactive":
        tapped = (msg.payload or {}).get("id") or ""
        level = tapped.split(":", 1)[1] if tapped.startswith("edu:") else None
        return level if level in EDUCATION_LEVELS else None
    if msg.kind == "text":
        typed = campaign_buttons.key(msg.body)
        for level in EDUCATION_LEVELS:
            labels = {campaign_buttons.key(m[_EDU_KEYS[level]]) for m in MESSAGES.values()}
            if typed in labels or typed in _EDU_TYPED[level]:
                return level
    return None


def _ask_language(db, conv, flow: str):
    options = language_options(_campaign_lang(db, conv))
    prompts = []
    for code in options:
        line = bot_messages.text(code, "language_prompt")
        if line not in prompts:
            prompts.append(line)
    _move(conv, CHOOSE_LANG, next=flow)
    _say(db, conv, "\n".join(prompts),
         buttons=[{"id": f"lang:{c}", "title": LANGUAGE_NAMES[c]} for c in options])


def _ask_language_again(db, conv):
    options = language_options(_campaign_lang(db, conv))
    prompts = []
    for code in options:
        line = bot_messages.text(code, "language_prompt")
        if line not in prompts:
            prompts.append(line)
    _fallback(db, conv, "\n".join(prompts),
              buttons=[{"id": f"lang:{c}", "title": LANGUAGE_NAMES[c]} for c in options])


def _begin(db, conv, flow: str):
    """The first question of a flow, in the chosen language."""
    if flow == WEBINAR:
        _move(conv, AWAIT_WEBINAR)
        _say(db, conv, _t(db, conv, "webinar_ask"), buttons=YES_NO("webinar", _lang(db, conv)))
    else:
        _move(conv, AWAIT_PIN, pin_attempts=0)
        _say(db, conv, _t(db, conv, "ask_pin"))


def _start(db, conv, msg, flow: str):
    """A campaign button was tapped: start that flow, asking the language if not known."""
    if flow == ONBOARD and conv.documents_submitted_at:
        _say(db, conv, _t(db, conv, "already_submitted"))
        return
    # Tapping a button again starts over, but what the person already told
    # us (their language, their webinar answer) is kept.
    kept = {k: v for k, v in (conv.bot_data or {}).items() if k in _REMEMBERED}
    conv.bot_data = {**kept, "trigger": msg.body}
    if _chosen_lang(db, conv):
        _begin(db, conv, flow)
    else:
        _ask_language(db, conv, flow)


def _send_upload_link(db, conv):
    """Send the upload link, issuing a fresh one if there is none or it lapsed."""
    expires = inbox.aware(conv.upload_token_expires_at)
    if not conv.upload_token or not expires or expires <= inbox.now():
        conv.upload_token = secrets.token_urlsafe(24)
        conv.upload_token_expires_at = inbox.now() + timedelta(days=UPLOAD_LINK_DAYS)
    _move(conv, AWAIT_UPLOAD)
    _say(db, conv, _t(db, conv, "send_link"),
         link={"text": _t(db, conv, "link_button"), "url": upload_url(conv)})


def _pin_failed(db, conv, reply: str):
    attempts = (conv.bot_data or {}).get("pin_attempts", 0) + 1
    if attempts >= MAX_PIN_ATTEMPTS:
        _move(conv, HANDOVER, pin_attempts=attempts)
        _say(db, conv, _t(db, conv, "handover"))
    else:
        _move(conv, AWAIT_PIN, pin_attempts=attempts)
        _say(db, conv, reply)


def _on_pin(db, conv, msg):
    pin = pincode_coverage.extract_pincode(msg.body) if msg.kind == "text" else None
    if not pin:
        _pin_failed(db, conv, _t(db, conv, "bad_pin"))
        return

    result = pincode_coverage.check(db, pin)
    logger.info(f"onboarding_bot event=PIN_CHECKED pin={pin} result={result['status']} "
                f"km={result.get('distance_km')}")
    if result["status"] == "unknown":
        _pin_failed(db, conv, _t(db, conv, "unknown_pin", pin=pin))
        return

    coverage = {k: result.get(k) for k in ("pincode", "nearest_pincode", "distance_km", "place")}
    if result["status"] == "served":
        _move(conv, AWAIT_EDUCATION, coverage=coverage)
        _say(db, conv, _t(db, conv, "ask_education"), buttons=education_buttons(_lang(db, conv)))
    else:
        _move(conv, NOT_SERVED, coverage=coverage)
        _say(db, conv, _t(db, conv, "not_served", pin=pin))


def _only_a_pin(msg: WhatsAppMessage) -> Optional[str]:
    """A PIN when the message is nothing but one; "500000" mid-sentence may be an amount."""
    body = re.sub(r"[\s-]", "", msg.body or "")
    return body if msg.kind == "text" and re.fullmatch(r"[1-9]\d{5}", body) else None


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


def _tell_team(conv, what: str, availability: Optional[str] = None):
    """Email the team a webinar answer, so somebody sends the link."""
    from src.services import auth_service, notifier

    try:
        notifier.notify_webinar(auth_service.BOOTSTRAP_ADMIN, {
            "name": conv.profile_name, "phone": conv.phone, "answer": what,
            "availability": availability, "language": LANGUAGE_NAMES.get((conv.bot_data or {}).get("lang")),
        })
    except Exception:
        logger.exception("onboarding_bot event=WEBINAR_NOTIFY_FAILED")


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
    if (msg.kind == "button" and is_trigger(msg.body, cfg["triggers"])) or tapped == START_INTERESTED:
        _understood(conv)
        _start(db, conv, msg, ONBOARD)
        return
    if (msg.kind == "button" and campaign_buttons.is_webinar(msg.body)) or tapped == START_WEBINAR:
        _understood(conv)
        _start(db, conv, msg, WEBINAR)
        return

    step = conv.bot_step

    if step == CHOOSE_LANG:
        code = _language_answer(msg)
        if code:
            _understood(conv)
            conv.bot_data = {**(conv.bot_data or {}), "lang": code,
                             "lang_campaign": _campaign_lang(db, conv)}
            _begin(db, conv, (conv.bot_data or {}).get("next") or ONBOARD)
        else:
            _ask_language_again(db, conv)
        return

    if step == AWAIT_AVAILABILITY:
        # Whatever they write is when they can attend.
        if msg.kind in ("text", "audio"):
            _understood(conv)
            said = msg.body if msg.kind == "text" else "(voice message — listen in the inbox)"
            _move(conv, WEBINAR_AVAILABILITY,
                  webinar={"answer": "availability", "availability": said, "at": inbox.now().isoformat()})
            _say(db, conv, _t(db, conv, "webinar_noted"))
            _tell_team(conv, "Not available tomorrow; shared their availability", said)
        else:
            _fallback(db, conv, _t(db, conv, "webinar_no"))
        return

    # A PIN code is checked whenever one is sent, not only when asked for:
    # someone told "not in your area" may well try another. Mid-question
    # only a message that is nothing but a PIN counts, so "yes, 500000"
    # is not read as one; once the upload link is out, the PIN is settled.
    if step not in (AWAIT_UPLOAD, SUBMITTED):
        pin = (_only_a_pin(msg) if step in (AWAIT_EDUCATION, AWAIT_FRANCHISE, AWAIT_INVEST,
                                             AWAIT_DOCS, AWAIT_WEBINAR)
               else pincode_coverage.extract_pincode(msg.body) if msg.kind == "text" else None)
        if pin:
            _understood(conv)
            _on_pin(db, conv, msg)
            return

    lang = _lang(db, conv)

    if step == AWAIT_PIN:
        # _on_pin counts the failed attempts and hands over after a few.
        if msg.kind == "text":
            _on_pin(db, conv, msg)
        else:
            _fallback(db, conv, _t(db, conv, "bad_pin"))

    elif step == AWAIT_EDUCATION:
        level = _education_answer(msg)
        if level == "other":
            _understood(conv)
            _move(conv, NOT_ELIGIBLE, education=level)
            _say(db, conv, _t(db, conv, "not_eligible"))
        elif level:
            _understood(conv)
            _move(conv, AWAIT_FRANCHISE, education=level)
            _say(db, conv, _t(db, conv, "ask_franchise"), buttons=YES_NO("franchise", lang))
        else:
            _fallback(db, conv, _t(db, conv, "ask_education"), buttons=education_buttons(lang))

    elif step == AWAIT_FRANCHISE:
        # Either answer goes on to the investment question; it is recorded
        # for the team, not used to turn anyone away.
        answer = _answer(msg, "franchise")
        if answer is not None:
            _understood(conv)
            _move(conv, AWAIT_INVEST, franchise=answer)
            _say(db, conv, _t(db, conv, "ask_invest"), buttons=YES_NO("invest", lang))
        else:
            _fallback(db, conv, _t(db, conv, "remind_choice") + "\n\n" + _t(db, conv, "ask_franchise"),
                      buttons=YES_NO("franchise", lang))

    elif step == AWAIT_INVEST:
        answer = _answer(msg, "invest")
        if answer is True:
            _understood(conv)
            _move(conv, AWAIT_DOCS, can_invest=True)
            _say(db, conv, _t(db, conv, "ask_docs", documents=document_list(lang)), buttons=YES_NO("docs", lang))
        elif answer is False:
            _understood(conv)
            _move(conv, NOT_INVESTING, can_invest=False)
            _say(db, conv, _t(db, conv, "not_investing"))
        else:
            _fallback(db, conv, _t(db, conv, "remind_choice") + "\n\n" + _t(db, conv, "ask_invest"),
                      buttons=YES_NO("invest", lang))

    elif step in (AWAIT_DOCS, AWAIT_UPLOAD):
        # At AWAIT_UPLOAD a second "Yes" means the link was lost; send it again.
        answer = _answer(msg, "docs")
        if answer is True:
            _understood(conv)
            _send_upload_link(db, conv)
        elif answer is False and step == AWAIT_DOCS:
            _understood(conv)
            _move(conv, AWAIT_DOCS, has_documents=False)
            _say(db, conv, _t(db, conv, "docs_later"))
        elif step == AWAIT_DOCS:
            _fallback(db, conv, _t(db, conv, "remind_choice") + "\n\n"
                      + _t(db, conv, "ask_docs", documents=document_list(lang)), buttons=YES_NO("docs", lang))
        else:
            _fallback(db, conv, _t(db, conv, "remind_upload"),
                      link={"text": _t(db, conv, "link_button"), "url": upload_url(conv)})

    elif step == AWAIT_WEBINAR:
        answer = _answer(msg, "webinar")
        if answer is True:
            _understood(conv)
            _move(conv, WEBINAR_CONFIRMED, webinar={"answer": "yes", "at": inbox.now().isoformat()})
            _say(db, conv, _t(db, conv, "webinar_yes"))
            _tell_team(conv, "Confirmed for tomorrow's webinar")
        elif answer is False:
            _understood(conv)
            _move(conv, AWAIT_AVAILABILITY)
            _say(db, conv, _t(db, conv, "webinar_no"))
        else:
            _fallback(db, conv, _t(db, conv, "remind_choice") + "\n\n" + _t(db, conv, "webinar_ask"),
                      buttons=YES_NO("webinar", lang))

    elif step == SUBMITTED:
        _fallback(db, conv, _t(db, conv, "already_submitted"))

    elif step == NOT_SERVED:
        pin = ((conv.bot_data or {}).get("coverage") or {}).get("pincode") or "—"
        _fallback(db, conv, _t(db, conv, "not_served_again", pin=pin))

    elif step == NOT_ELIGIBLE:
        _fallback(db, conv, _t(db, conv, "not_eligible"))

    elif step in (NOT_INVESTING, HANDOVER, WEBINAR_CONFIRMED, WEBINAR_AVAILABILITY):
        _fallback(db, conv, _t(db, conv, "acknowledge"))

    else:
        # Never started: someone writing to the number of their own accord,
        # or answering a campaign with a button other than the two above.
        if msg.kind == "button":
            _fallback(db, conv, _t(db, conv, "acknowledge"))
        else:
            webinar = campaign_buttons.webinar_label(lang)
            _fallback(db, conv, _t(db, conv, "greeting", webinar=webinar), gap=GREETING_GAP,
                      buttons=[{"id": START_INTERESTED, "title": campaign_buttons.INTERESTED},
                               {"id": START_WEBINAR, "title": webinar}])


def documents_submitted(db: Session, conv: WhatsAppConversation) -> WhatsAppMessage:
    """The upload page was submitted: thank the person in the chat."""
    conv.documents_submitted_at = inbox.now()
    _move(conv, SUBMITTED)
    return _say(db, conv, _t(db, conv, "thanks"))


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
