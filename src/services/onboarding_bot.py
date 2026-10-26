"""
The onboarding bot: what happens after someone taps a campaign's buttons.

    tap "Interested"        -> choose a language: English / Hindi / theirs
      language chosen       -> ask for their PIN code
      PIN within our area   -> "How far have you studied?"
                                 [12th/Diploma] [Graduate/Post-Grad] [Other]
      Other                 -> "Sorry, at least 12th or a Diploma is needed" (ends)
      12th or Graduate      -> "Can you invest 5 lakh to set up a franchise
                               business?" (with what a franchise is) [Yes] [No]
      Yes                   -> the documents needed, "Have them?"   [Yes] [No]
      Yes                   -> a link to the upload page
      documents submitted   -> "Thank you, our team will reach out"

    tap "Personal Guidance Chahiye" -> choose a language
      language chosen       -> "Available for personal guidance tomorrow?" [Yes] [No]
      Yes                   -> "Our team will contact you soon"
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
import contextvars
import json
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.models.app_setting import AppSetting
from src.models.inbox import WhatsAppConversation, WhatsAppMessage
from src.services import eko_knowledge
from src.services import bot_messages, campaign_buttons, inbox, pincode_coverage
from src.services.bot_messages import LANGUAGE_NAMES, LANGUAGE_WORDS, MESSAGES, QUESTION_WORDS

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
# Personal guidance since 2026-10-21: the person asks, the bot answers what it
# knows and leaves the rest to a person, until they say they are interested.
GUIDANCE_QA = "GUIDANCE_QA"

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
    AWAIT_WEBINAR: "Asked about personal guidance",
    AWAIT_AVAILABILITY: "Asked guidance availability",
    WEBINAR_CONFIRMED: "Personal guidance confirmed",
    WEBINAR_AVAILABILITY: "Guidance time shared",
    GUIDANCE_QA: "Personal guidance: asking questions",
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
# A question or a voice note is answered past that limit (it is a person
# asking, not an auto-reply), up to this many in a row...
MAX_QUESTION_STREAK = 10
# ...and a run of either is forgotten after this long without one, so a
# person who comes back later is answered again.
STREAK_RESET = timedelta(hours=1)

# Personal guidance is offered for the same day to someone who taps its
# button before this hour (India time), and for the next day after it.
GUIDANCE_TODAY_UNTIL = 18
IST = timezone(timedelta(hours=5, minutes=30))

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


def latest_campaign_name(db: Session, phone: str) -> Optional[str]:
    """The name of the newest campaign sent to this number, to tag the website link with."""
    from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient

    row = (db.query(WhatsAppCampaign.name)
           .join(WhatsAppCampaignRecipient, WhatsAppCampaignRecipient.campaign_id == WhatsAppCampaign.campaign_id)
           .filter(WhatsAppCampaignRecipient.phone == phone)
           .order_by(WhatsAppCampaignRecipient.created_at.desc()).first())
    return row[0] if row else None


def latest_send(db: Session, phone: str):
    """(recipient, template) for the newest campaign message Meta accepted for this number, or None."""
    from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient, WhatsAppTemplate

    return (db.query(WhatsAppCampaignRecipient, WhatsAppTemplate)
            .join(WhatsAppCampaign, WhatsAppCampaign.campaign_id == WhatsAppCampaignRecipient.campaign_id)
            .join(WhatsAppTemplate, WhatsAppTemplate.template_id == WhatsAppCampaign.template_id)
            .filter(WhatsAppCampaignRecipient.phone == phone,
                    (WhatsAppCampaignRecipient.provider_message_id.isnot(None))
                    | (WhatsAppCampaignRecipient.status == "PROCESSING"))
            .order_by(WhatsAppCampaignRecipient.sent_at.desc().nullslast(),
                      WhatsAppCampaignRecipient.created_at.desc())
            .first())


def campaign_text(rec, template) -> str:
    """The campaign's words as this person was sent them, placeholders filled."""
    from src.services.whatsapp_service import parameter_value, template_placeholders

    body = template.body or ""
    for placeholder in template_placeholders(template):
        body = body.replace(placeholder, parameter_value(rec, placeholder, template))
    return body.strip()


def _campaign_buttons(db, template, lang) -> list:
    """The campaign's two quick replies as buttons the bot can act on."""
    triggers = get_settings(db)["triggers"]
    buttons = []
    for b in template.buttons or []:
        text = (b or {}).get("text") if isinstance(b, dict) else None
        if not text or (b.get("type") or "QUICK_REPLY") != "QUICK_REPLY":
            continue
        if is_trigger(text, triggers) and START_INTERESTED not in [x["id"] for x in buttons]:
            buttons.append({"id": START_INTERESTED, "title": text[:campaign_buttons.REPLY_BUTTON_LIMIT]})
        elif campaign_buttons.is_webinar(text) and START_WEBINAR not in [x["id"] for x in buttons]:
            title = text if len(text) <= campaign_buttons.REPLY_BUTTON_LIMIT else campaign_buttons.webinar_title(lang)
            buttons.append({"id": START_WEBINAR, "title": title})
    # A template without them still gets the two ways forward.
    return buttons or [{"id": START_INTERESTED, "title": campaign_buttons.INTERESTED},
                       {"id": START_WEBINAR, "title": campaign_buttons.webinar_title(lang)}]


def _auto_reply(db, conv, msg) -> bool:
    """
    Their business's own bot answered our campaign ("Thank you for reaching
    out… we will get back to you shortly"): the campaign's text goes again,
    with its two buttons, so it is what the owner sees when they open the
    chat (the user, 2026-10-26). Once per campaign message, so two bots
    cannot answer each other. True if it was an auto-reply.
    """
    if conv.bot_step or msg.kind != "text":
        return False
    sent = latest_send(db, conv.phone)
    if sent is None:
        return False
    rec, template = sent
    from src.services import auto_replies
    if not auto_replies.is_automatic(msg.body, inbox.aware(rec.sent_at),
                                     inbox.aware(getattr(msg, "created_at", None)) or inbox.now()):
        return False
    if isinstance(msg, WhatsAppMessage):
        # Not a reply from them: Campaign insights leaves it out of "replied".
        msg.payload = {**(msg.payload or {}), "auto_reply": True}
    data = conv.bot_data or {}
    if data.get("auto_reply_for") == rec.recipient_id:
        # Already sent again for this campaign message: their bot's second word is left be.
        return True
    conv.bot_data = {**data, "auto_reply_for": rec.recipient_id, "auto_reply_at": inbox.now().isoformat()}
    text = campaign_text(rec, template)
    if text:
        _say(db, conv, text[:1024], buttons=_campaign_buttons(db, template, _lang(db, conv)))
    logger.info(f"onboarding_bot event=AUTO_REPLY phone=...{conv.phone[-4:]} "
                f"phrase={auto_replies.matched(msg.body)!r} resent={bool(text)}")
    return True


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
    lang = _lang(db, conv)
    # Hindi to someone who writes it in Latin letters: in the same letters.
    if lang == "hi" and (conv.bot_data or {}).get("script") == "latin" and key in bot_messages.HINGLISH:
        text = bot_messages.HINGLISH[key]
        return text.format(**fields) if fields else text
    return bot_messages.text(lang, key, **fields)


def _note_script(conv, msg) -> None:
    """
    Remember whether the person writes in Latin letters or in an Indic script.

    A sentence counts, not one word ("Hindi", typed to choose the language,
    says nothing about how they write); a voice note is answered in the
    script of its language.
    """
    kind = getattr(msg, "kind", None)
    if kind == "audio" or getattr(msg, "voice", False):
        script = "indic"
    else:
        said = message_text(msg) if kind == "text" else None
        if not said or len(re.findall(r"\w+", said)) < 2:
            return
        if re.search(r"[ऀ-෿]", said):
            script = "indic"
        elif re.search(r"[A-Za-z]{2,}", said):
            script = "latin"
        else:
            return
    if (conv.bot_data or {}).get("script") != script:
        conv.bot_data = {**(conv.bot_data or {}), "script": script}


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
        return education_in_words(msg.body)
    return None


# Indic digits as the ASCII ones: "ધોરણ ૧૨", "१२वीं".
_DIGITS = str.maketrans("०१२३४५६७८९૦૧૨૩૪૫૬૭૮૯੦੧੨੩੪੫੬੭੮੯০১২৩৪৫৬৭৮৯", "0123456789" * 4)
# Words for each level, as people type them in any of the bot's languages.
_EDU_WORDS = {
    "grad": ("graduat", "degree", "bachelor", "postgrad", "master", "bcom", "b com", "bsc", "b sc", "btech", "b tech",
             "mba", "mca", "bca", "llb", "b ed", "bed ", "m com", "mcom", "msc", "college pass", "स्नातक", "ग्रेजुएट",
             "ग्रैजुएट", "ડિગ્રી", "સ્નાતક", "ગ્રેજ્યુએટ", "ਗ੍ਰੈਜੂਏਟ", "ਡਿਗਰੀ", "पदवी", "पदवीधर"),
    # Short words only as whole words: "inter" is in "interested", "iti" in "position".
    "12": ("12th", "12 th", "12 pass", "12vi", "12 vi", "12वी", "12वीं", "class 12", " inter ", "intermediate", " hsc ",
           "diploma", " iti ", "polytechnic", " puc ", "college", "कॉलेज", "કોલેજ", "barvi", "barhvi", "barahvi", "बारहवीं", "बारवीं", "डिप्लोमा", "ધોરણ 12", "બારમું",
           "બાર ", "ડિપ્લોમા", "ਬਾਰ੍ਹਵੀਂ", "ਡਿਪਲੋਮਾ", "बारावी"),
    "other": ("10th", "10 th", "10 pass", "matric", "sslc", "dasvi", "दसवीं", "દસમું", "ਦਸਵੀਂ", "8th", "9th",
              "11th", "not studied", "no study", "padhai nahi", "पढ़ाई नहीं", "अनपढ़", "illiterate"),
}


def education_in_words(text: Optional[str]) -> Optional[str]:
    """
    An education level typed in the person's own words: "13", "12 pass",
    "ધોરણ ૧૨", "BCom", "बारहवीं". A number is years of schooling: up to 11 is
    below 12th; 12 to 14 is 12th and some college; 15 and above a graduate.
    None when it says no level, so the question is asked again.
    """
    if not text:
        return None
    said = f" {' '.join(text.lower().translate(_DIGITS).replace('.', ' ').split())} "
    for level in ("grad", "12", "other"):
        if any(w in said for w in _EDU_WORDS[level]):
            return level
    numbers = [int(n) for n in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", said)]
    years = [n for n in numbers if 1 <= n <= 20]
    if len(said.split()) <= 6 and years:
        n = years[0]
        return "other" if n <= 11 else "12" if n <= 14 else "grad"
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
        # Not a booking: an invitation to ask, and a way to start when ready.
        _move(conv, GUIDANCE_QA)
        _say(db, conv, _t(db, conv, "guidance_open"), buttons=_interested_button())
    else:
        _move(conv, AWAIT_PIN, pin_attempts=0)
        _say(db, conv, _t(db, conv, "ask_pin"))


def _interested_button() -> list:
    return [{"id": START_INTERESTED, "title": campaign_buttons.INTERESTED}]


# Saying they want to start, in their own words, while asking questions.
_START_WORDS = {"interested", "intrested", "intersted", "interseted", "intrsted", "इंटरेस्टेड", "इच्छुक", "ઇન્ટરેસ્ટેડ",
                "ਇੰਟਰੈਸਟਡ"}
_START_PHRASES = ("judna hai", "judna chahta", "judna chahti", "jodna hai", "shuru karna hai", "shuru karna chahta",
                  "shuru karna chahti", "start karna hai", "apply karna hai", "csp chahiye", "csp lena hai",
                  "kiosk chahiye", "kiosk lena hai", "i want to start", "i want to apply", "i want to join", "main taiyar",
                  "mai taiyar", "main tayar", "mai tayar", "ready hun", "ready hoon", "ready hu", "जुड़ना है", "शुरू करना है",
                  "ਸ਼ੁਰੂ ਕਰਨਾ", "શરૂ કરવું છે")
_NOT_NOW = ("not interested", "interested nahi", "interested nhi", "nahi chahiye", "nhi chahiye", "nahi karna",
            "nhi karna", "abhi nahi", "no thanks", "नहीं चाहिए", "इंटरेस्टेड नहीं")


def wants_to_start(text: Optional[str]) -> bool:
    """Whether someone asking about personal guidance says they want to begin the application."""
    said = " " + " ".join(re.findall(r"[\w\u0900-\u0DFF]+", (text or "").lower())) + " "
    if any(f" {p} " in said for p in _NOT_NOW):
        return False
    if any(f" {w} " in said for w in _START_WORDS):
        return True
    return any(f" {p} " in said for p in _START_PHRASES)


def _guidance_reply(db, conv, msg) -> None:
    """
    Personal guidance: answer a question from Eko's FAQ, kindly; leave one it
    does not cover to a person; begin the application when they want to.
    """
    said = message_text(msg)
    if said and wants_to_start(said):
        _understood(conv)
        _start(db, conv, msg, ONBOARD)
        return
    # A PIN code on its own: they are checking whether we serve them, so the
    # application begins with it.
    if _only_a_pin(msg):
        _understood(conv)
        kept = {k: v for k, v in (conv.bot_data or {}).items() if k in _REMEMBERED}
        conv.bot_data = {**kept, "trigger": "PIN during personal guidance"}
        _move(conv, AWAIT_PIN, pin_attempts=0)
        _on_pin(db, conv, msg)
        return
    _fallback(db, conv, _t(db, conv, "guidance_more"), buttons=_interested_button(), kind_intro=True)


def _guidance_day(conv) -> str:
    """"today" or "tomorrow": the day personal guidance was offered for."""
    return (conv.bot_data or {}).get("guidance_day") or "tomorrow"


def _guidance_ask(db, conv) -> str:
    key = "webinar_ask_today" if _guidance_day(conv) == "today" else "webinar_ask"
    return _t(db, conv, key)


def _ask_invest(db, conv, lang):
    """What the ₹3–5 lakh is for, then the question: the money stays theirs, in an e-wallet."""
    _say(db, conv, _t(db, conv, "invest_explained"))
    _say(db, conv, _t(db, conv, "ask_invest"), buttons=YES_NO("invest", lang))


def _start(db, conv, msg, flow: str):
    """A campaign button was tapped: start that flow, asking the language if not known."""
    if flow == ONBOARD and conv.documents_submitted_at:
        _say(db, conv, _t(db, conv, "already_submitted"))
        return
    # Tapping a button again starts over, but what the person already told
    # us (their language, their webinar answer) is kept.
    kept = {k: v for k, v in (conv.bot_data or {}).items() if k in _REMEMBERED}
    conv.bot_data = {**kept, "trigger": msg.body}
    if flow == WEBINAR:
        # Decided once, when the button is tapped, so a reminder or the
        # question asked again later names the same day.
        tapped_at = inbox.aware(getattr(msg, "created_at", None)) or inbox.now()
        today = tapped_at.astimezone(IST).hour < GUIDANCE_TODAY_UNTIL
        conv.bot_data = {**conv.bot_data, "guidance_day": "today" if today else "tomorrow"}
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
    first = conv.bot_step != AWAIT_UPLOAD
    _move(conv, AWAIT_UPLOAD)
    sent = _say(db, conv, _t(db, conv, "send_link"),
                link={"text": _t(db, conv, "link_button"), "url": upload_url(conv)})
    if first and not conv.documents_submitted_at:
        # The sheet's "Documents pending" (owner DCs/Bot): follow up until they upload.
        # This message is its notification; a reminder follows in 2 days (2026-10-22).
        from src.services import followups, handover
        handover.record(db, conv, "int_docs_pending", "bot", note="Upload link sent", run_now=False)
        followups.mark_sent(db, conv, "docs_reminder", sent)


def _pin_failed(db, conv, reply: str):
    attempts = (conv.bot_data or {}).get("pin_attempts", 0) + 1
    if attempts >= MAX_PIN_ATTEMPTS:
        _move(conv, HANDOVER, pin_attempts=attempts)
        flag(conv, "Could not give a usable PIN code after three tries")
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
    coverage["served"] = result["status"] == "served"
    # A real PIN outside our SBI branch area no longer ends the journey (the
    # user, 2026-10-23): they carry on, and are kept with the qualified leads as
    # "Not qualified for SBI branch code", for another proposal (BT, HDFC...).
    # A PIN that cannot be found anywhere is still asked for again, above.
    _move(conv, AWAIT_EDUCATION, coverage=coverage)
    _say(db, conv, _t(db, conv, "ask_education"), buttons=education_buttons(_lang(db, conv)))


def _only_a_pin(msg: WhatsAppMessage) -> Optional[str]:
    """A PIN when the message is nothing but one; "500000" mid-sentence may be an amount."""
    body = re.sub(r"[\s-]", "", msg.body or "")
    return body if msg.kind == "text" and re.fullmatch(r"[1-9]\d{5}", body) else None


# The message being answered, so that _fallback can tell a question from an
# unclear answer without every caller passing it along.
_CURRENT = contextvars.ContextVar("onboarding_bot_message", default=None)


def message_text(msg) -> Optional[str]:
    """What someone said: their text, or what their voice note was transcribed as."""
    if msg is None:
        return None
    if msg.kind == "text":
        return msg.body
    if msg.kind == "audio":
        return (msg.payload or {}).get("transcript")
    return None


def looks_like_question(text: Optional[str]) -> bool:
    """
    Whether a message asks something the bot cannot answer itself.

    A question mark, a question word in any of the bot's languages, or a
    message long enough to be more than a one-word reply. "ok", "thanks" and
    "hello" are none of these.
    """
    text = (text or "").strip()
    if not text:
        return False
    if "?" in text or "？" in text:
        return True
    words = re.findall(r"[\w'\u0900-\u0DFF]+", text.lower())
    if any(w in QUESTION_WORDS for w in words):
        return True
    return len(words) >= 8


def flag(conv, reason: str) -> None:
    """
    Mark the conversation for a person. Only ever cleared by someone pressing
    "Question resolved"; asked again, the latest question is what shows.
    """
    conv.needs_attention = True
    conv.attention_reason = (reason or "").strip()[:500] or None
    conv.attention_at = inbox.now()
    conv.attention_resolved_by = None
    conv.attention_resolved_at = None


def _fallback(db, conv, body, gap=FALLBACK_GAP, kind_intro=False, **kw):
    """
    Answer a message the bot did not understand, if it has not just done so.

    Paced, and stopped after a few in a row, so that a person typing several
    lines gets one answer and an auto-reply cannot start an endless exchange.

    A question of their own, or a voice note, marks the conversation for a
    person and is thanked first, inside the pause and past the few-in-a-row
    limit (up to MAX_QUESTION_STREAK): a question deserves an answer. A run
    is forgotten after STREAK_RESET.
    """
    data = conv.bot_data or {}
    streak = data.get("fallback_streak", 0)
    last = data.get("fallback_at")
    current = _CURRENT.get()
    said = message_text(current)
    # A voice note the bot could not act on is always left for a person: a
    # machine transcript of a short note can be wrong, and only someone
    # listening can tell what was asked.
    voice = getattr(current, "voice", False) or getattr(current, "kind", None) == "audio"
    # A question Eko's confirmed FAQ answers is answered here and now; the
    # question it was asked at, if any, follows. Anything else, and any voice
    # note (a transcript can be wrong), is left for a person.
    faq = eko_knowledge.match(said) if said else []
    # Fearing Eko is a fraud: always the answer about who Eko is, with the website.
    doubts = eko_knowledge.distrust(said)
    from src.services import agent_controls
    if not agent_controls.is_on(db, "bot_faq"):
        # Turned off by the admin: no answer from the bot; the question goes to a person.
        faq, doubts = [], []
    if doubts and "real" not in faq:
        faq = ["real"] + list(faq)
    asked = looks_like_question(said) or voice or bool(faq)
    if faq:
        answer = eko_knowledge.reply(faq, _lang(db, conv), said, campaign=latest_campaign_name(db, conv.phone))
        if kind_intro:
            answer = f"{_t(db, conv, 'guidance_intro')} {answer}"
        if "investment" in faq:
            # How much, then what the money is for: it stays theirs.
            answer += "\n\n" + _t(db, conv, "invest_explained")
        # The run, with the FAQ entries it answered from (agent_telemetry).
        from src.services import agent_telemetry
        agent_telemetry.log(db, "bot_faq", "chat", conv.phone, answer, prompt=said, context=[
            agent_telemetry.chunk("faq", f"{eko_knowledge._BY_ID[i]['question']} → "
                                         f"{eko_knowledge.answer(i, _lang(db, conv), said)}", i) for i in faq
            if i in eko_knowledge._BY_ID] + ([agent_telemetry.chunk("trust_rule", "They doubt Eko is genuine")]
                                             if doubts else []))
        conv.bot_data = {**(conv.bot_data or {}), "faq_answered": (data.get("faq_answered") or []) + faq}
        data = conv.bot_data
        if doubts:
            # Answered, and a person calls them too: trust is won on a call, not by a bot.
            step = STEP_LABELS.get(conv.bot_step, conv.bot_step or "not started")
            near_end = " (the last step before their documents)" if conv.bot_step in (AWAIT_UPLOAD, AWAIT_DOCS) else ""
            # Recorded as "Trust concern": the team gets a ticket and an email two hours on,
            # an hour after the bot's reminder, unless the documents come in first
            # (the user, 2026-10-23).
            from src.services import dispositions as dz, handover
            if dz.normalise(conv.disposition) != "int_trust":
                handover.record(db, conv, "int_trust", "bot", run_now=False,
                                note=f"They worry Eko may be fake. At: {step}{near_end}. They wrote: "
                                     f"“{(said or '')[:200]}”. The bot sent who Eko is, the website and our "
                                     f"number to call.")
            if conv.bot_step == AWAIT_DOCS:
                # At the documents question the trust answer ends, as it does once the link is
                # out, with the upload line and its link (the user, 2026-10-22); they stay at the
                # question, so their Yes or No still counts.
                if not conv.upload_token or not inbox.aware(conv.upload_token_expires_at) or \
                        inbox.aware(conv.upload_token_expires_at) <= inbox.now():
                    conv.upload_token = secrets.token_urlsafe(24)
                    conv.upload_token_expires_at = inbox.now() + timedelta(days=UPLOAD_LINK_DAYS)
                body = _t(db, conv, "remind_upload")
                kw = {"link": {"text": _t(db, conv, "link_button"), "url": upload_url(conv)}}
        elif voice:
            # A transcript can be wrong: answered, and still left for a person to check.
            flag(conv, f"Voice note: {said} (answered from the FAQ: {', '.join(faq)})")
        else:
            # The bot answered it itself: a ticket solved by the bot, with its answer.
            from src.services import tickets
            tickets.answered_by_bot(db, conv, said, answer)
        body = answer if body == _t(db, conv, "acknowledge") else f"{answer}\n\n{body}"
    elif asked:
        flag(conv, f"Voice note: {said}" if voice and said else ("Voice note" if voice else said))
        ack = _t(db, conv, "question_ack")
        body = ack if body == _t(db, conv, "acknowledge") else f"{ack}\n\n{body}"
    if last and inbox.now() - datetime.fromisoformat(last) >= STREAK_RESET:
        streak = 0
    if streak >= (MAX_QUESTION_STREAK if asked else MAX_FALLBACK_STREAK):
        return
    if not asked and last and inbox.now() - datetime.fromisoformat(last) < gap:
        return
    conv.bot_data = {**data, "fallback_streak": streak + 1, "fallback_at": inbox.now().isoformat()}
    _say(db, conv, body, **kw)


def _understood(conv):
    """The person said something the bot could act on; any pacing starts afresh."""
    data = conv.bot_data or {}
    if data.get("fallback_streak") or data.get("fallback_at"):
        conv.bot_data = {k: v for k, v in data.items() if k not in ("fallback_streak", "fallback_at")}


class _Spoken:
    """A voice note read as the text it was transcribed to, for the bot's purposes only."""

    voice = True

    def __init__(self, msg, text):
        self.message_id, self.direction, self.phone = msg.message_id, msg.direction, msg.phone
        self.kind, self.body, self.payload = "text", text, msg.payload


def handle(db: Session, conv: WhatsAppConversation, msg: WhatsAppMessage) -> None:
    """Answer one inbound message. Every message gets a fitting reply, paced."""
    if msg.direction != "IN":
        return
    # The number is shared with other teams, who talk to people of their
    # own. The bot speaks only to people an AutoGMap campaign reached, and
    # only their questions are marked for attention; every other
    # conversation is still shown in the inbox, and left to a person.
    if not (inbox.from_campaign(db, conv.phone) or inbox.being_sent(db, conv.phone)):
        return
    if not (conv.bot_data or {}).get("campaign"):
        # Remembered, so the chat is never shown as an enquiry of their own (handover.bot_disposition).
        conv.bot_data = {**(conv.bot_data or {}), "campaign": True}

    # A file that can carry malware (a .zip, a program...) is blocked, not
    # answered: the chat goes to a person with a ticket, so the team knows.
    blocked = inbox.unsafe_reason(msg.payload) if msg.kind in inbox.MEDIA_KINDS else None
    if blocked:
        name = (msg.payload or {}).get("filename") or "a file"
        flag(conv, f"Unsafe file blocked: {name} ({blocked}). Do not ask for it again; treat it as suspicious.")
        from src.services import tickets
        tickets.raise_or_update(db, conv)
        email_attention(db, conv)
        return

    # A voice note is answered as what it says, in the language it was said in.
    if msg.kind == "audio" and message_text(msg):
        spoken = (msg.payload or {}).get("language")
        if spoken in MESSAGES:
            conv.bot_data = {**(conv.bot_data or {}), "lang": spoken,
                             "lang_campaign": _campaign_lang(db, conv)}
        msg = _Spoken(msg, message_text(msg))

    _note_script(conv, msg)
    flagged_before = inbox.aware(conv.attention_at) if conv.needs_attention else None
    token = _CURRENT.set(msg)
    try:
        cfg = get_settings(db)
        if conv.bot_paused or not cfg["enabled"]:
            # Nobody automatic will answer, so a question or a voice note is
            # left for a person.
            voice = getattr(msg, "voice", False) or msg.kind == "audio"
            if voice or looks_like_question(message_text(msg)):
                flag(conv, message_text(msg) or "Voice note")
        else:
            _handle(db, conv, msg, cfg)
    finally:
        _CURRENT.reset(token)
    # Newly left for a person (or for a new reason): a ticket, and an email to the admin.
    if conv.needs_attention and inbox.aware(conv.attention_at) != flagged_before:
        from src.services import tickets
        tickets.raise_or_update(db, conv)
        email_attention(db, conv)


def _answers_the_step(conv, msg) -> bool:
    """Whether the message answers the question the bot is waiting on (a No to "can you invest?" is one)."""
    step = conv.bot_step
    if _only_a_pin(msg):
        return True
    if step == CHOOSE_LANG:
        return _language_answer(msg) is not None
    if step == AWAIT_PIN:
        return msg.kind == "text" and pincode_coverage.extract_pincode(msg.body) is not None
    if step in (AWAIT_EDUCATION, NOT_ELIGIBLE):
        return _education_answer(msg) is not None
    prefix = {AWAIT_FRANCHISE: "franchise", AWAIT_INVEST: "invest", AWAIT_DOCS: "docs", AWAIT_UPLOAD: "docs"}.get(step)
    return bool(prefix) and _answer(msg, prefix) is not None


def _reply_disposition(db, conv, msg) -> bool:
    """
    A reply that says where they stand ("abhi busy hoon, 5 baje call karna",
    "galti se apply ho gaya", "wrong number") is recorded as its disposition by
    the bot, by fixed rules (reply_dispositions.py; the user's sheet,
    2026-10-23), and the disposition's message is the reply. Not for an answer
    to the bot's question, a question of their own (the FAQ and the team take
    those), or a voice note, whose transcript can be wrong. True if recorded.
    """
    from src.services import agent_controls
    if not agent_controls.is_on(db, "bot_reply_disposition"):
        return False
    if msg.kind != "text" or getattr(msg, "voice", False) or _answers_the_step(conv, msg):
        return False
    said = (msg.body or "").strip()
    # A question goes to the FAQ and the team; a statement that happens to name an FAQ
    # subject ("meri cibil kharab hai") still says where they stand (the golden set, 2026-10-26).
    if (not said or "?" in said or eko_knowledge.distrust(said)
            or (eko_knowledge.asks(said) and eko_knowledge.match(said))):
        return False
    from src.services import learning_loop, reply_dispositions
    # A rule the admin accepted from the team's corrections comes first (learning_loop).
    learned = learning_loop.learned_reading(db, said)
    if learned:
        when = (reply_dispositions.call_time(said, inbox.now()) if learned in ("busy_at_time", "int_callback")
                else reply_dispositions.follow_up_date(said, inbox.now()) if learned.startswith("hold_") else None)
        hit = (learned, when)
    else:
        hit = reply_dispositions.detect(said)
    if not hit:
        return False
    key, when = hit
    from src.services import agent_telemetry, dispositions as dz, handover, nudge_messages, reply_language
    _understood(conv)
    guards = [
        {"name": "Not an answer to the bot's own question", "passed": True, "detail": f"Step {conv.bot_step or 'none'}"},
        {"name": "Not a question of theirs (left for the FAQ)", "passed": True, "detail": "No “?”, not asking an FAQ"},
        {"name": "Not a voice note (a transcript can be wrong)", "passed": True, "detail": "Typed text"},
    ]
    # Read two ways ("busy hoon, not interested"): the bot does not guess. A person
    # clarifies, with a ticket; they hear their message reached the team (2026-10-26).
    readings = [] if learned else reply_dispositions.ambiguous(said)
    if readings:
        labels = " or ".join(dz.label(k) for k in readings)
        flag(conv, f"Clarify: “{said[:200]}” could mean {labels}. Record the right disposition.")
        _say(db, conv, _t(db, conv, "acknowledge"))
        agent_telemetry.log(db, "bot_reply_disposition", "chat", conv.phone, "clarify", prompt=said, context=[
            agent_telemetry.chunk("rule", reply_dispositions.matched_phrase(said, k) or "", k) for k in readings],
            evaluation={"checks": guards + [{"name": "One meaning only", "passed": False,
                                             "detail": f"Could be {labels}: left for a person"}],
                        "ambiguous": readings})
        logger.info(f"onboarding_bot event=REPLY_AMBIGUOUS phone=...{conv.phone[-4:]} readings={readings}")
        return True
    sure = 0.95 if learned else reply_dispositions.confidence(said, key)
    logger.info(f"onboarding_bot event=REPLY_DISPOSITION phone=...{conv.phone[-4:]} key={key}")
    before = db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == conv.phone,
                                              WhatsAppMessage.direction == "OUT").count()
    handover.record(db, conv, key, "bot", note=f"They wrote: “{said[:200]}”", at=when)
    phrase = (said.strip().lower() if learned else reply_dispositions.matched_phrase(said, key)) or ""
    agent_telemetry.log(db, "bot_reply_disposition", "chat", conv.phone, key, prompt=said, context=[
        agent_telemetry.chunk("rule", phrase, key, score=sure),
        *([agent_telemetry.chunk("when", when.isoformat())] if when else [])], evaluation={
            "checks": guards + [{"name": "Confidence", "passed": sure >= reply_dispositions.CONFIDENT,
                                 "detail": f"{round(sure * 100)}% · read from “{phrase}”"
                                           + ("" if sure >= reply_dispositions.CONFIDENT else ": a single common word, worth a look")}],
            "confidence": sure})
    db.flush()
    sent = db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == conv.phone,
                                            WhatsAppMessage.direction == "OUT").count() > before
    if not sent and not dz.sub(key).closes:
        # Nothing goes out now (a check-back on a date): they still hear that it is noted.
        lang, latin = reply_language.last_reply(db, conv)
        _say(db, conv, nudge_messages.text("callback_confirm", nudge_messages.variant_for(lang, latin)))
    return True


def _handle(db: Session, conv: WhatsAppConversation, msg, cfg: dict) -> None:
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

    # Their own bot answered the campaign, not a person: the campaign goes again.
    if _auto_reply(db, conv, msg):
        return

    if _reply_disposition(db, conv, msg):
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

    # Personal guidance (and anyone still at the old availability questions):
    # their questions answered, until they want to start.
    if step in (GUIDANCE_QA, AWAIT_WEBINAR, AWAIT_AVAILABILITY):
        if step != GUIDANCE_QA:
            _move(conv, GUIDANCE_QA)
        _guidance_reply(db, conv, msg)
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
        # _on_pin counts the failed attempts and hands over after a few. A
        # question ("what is a PIN code?") is not a failed attempt: it is
        # thanked, left for a person, and the PIN asked for again.
        if msg.kind == "text" and looks_like_question(msg.body):
            _fallback(db, conv, _t(db, conv, "bad_pin"))
        elif msg.kind == "text":
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
            # One question now covers the investment and the franchise
            # (the user's choice, 2026-10-14).
            _understood(conv)
            _move(conv, AWAIT_INVEST, education=level)
            _ask_invest(db, conv, lang)
        else:
            _fallback(db, conv, _t(db, conv, "ask_education"), buttons=education_buttons(lang))

    elif step == AWAIT_FRANCHISE:
        # No longer asked on its own; kept for anyone left at this step
        # before the two questions became one. Either answer goes on.
        answer = _answer(msg, "franchise")
        if answer is not None:
            _understood(conv)
            _move(conv, AWAIT_INVEST, franchise=answer)
            _ask_invest(db, conv, lang)
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
            said = _say(db, conv, _t(db, conv, "not_investing"))
            # The sheet's "Investment issue": its reply offers the lower-investment
            # option, and the team hears so a person follows it up.
            from src.services import followups, handover
            handover.record(db, conv, "ni_investment", "bot", note="Said they cannot invest ₹3–5 lakh", run_now=False)
            followups.mark_sent(db, conv, "lower_investment", said)
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

    elif step == SUBMITTED:
        _fallback(db, conv, _t(db, conv, "already_submitted"))

    elif step == NOT_SERVED:
        # Told earlier that we are not near them: writing again, they now carry on
        # with the education question like anyone else (2026-10-23).
        _move(conv, AWAIT_EDUCATION)
        _say(db, conv, _t(db, conv, "ask_education"), buttons=education_buttons(_lang(db, conv)))

    elif step == NOT_ELIGIBLE:
        # Someone who tapped "Other" by mistake, or wrote "10" and then
        # their real level, can still answer again: a 12th/Diploma or a
        # degree carries on to the next question.
        level = _education_answer(msg)
        if level and level != "other":
            _understood(conv)
            _move(conv, AWAIT_INVEST, education=level)
            _ask_invest(db, conv, lang)
        else:
            _fallback(db, conv, _t(db, conv, "not_eligible"))

    elif step in (NOT_INVESTING, HANDOVER, WEBINAR_CONFIRMED, WEBINAR_AVAILABILITY):
        _fallback(db, conv, _t(db, conv, "acknowledge"))

    else:
        # Never started: someone writing to the number of their own accord,
        # or answering a campaign with a button other than the two above.
        if msg.kind == "button":
            _fallback(db, conv, _t(db, conv, "acknowledge"))
        else:
            webinar = campaign_buttons.webinar_title(lang)
            _fallback(db, conv, _t(db, conv, "greeting", webinar=webinar), gap=GREETING_GAP,
                      buttons=[{"id": START_INTERESTED, "title": campaign_buttons.INTERESTED},
                               {"id": START_WEBINAR, "title": webinar}])


# Steps where the bot is waiting for an answer; someone who goes quiet at one
# of these is nudged (see nudges.py).
NUDGE_STEPS = (CHOOSE_LANG, AWAIT_PIN, AWAIT_EDUCATION, AWAIT_FRANCHISE, AWAIT_INVEST,
               AWAIT_DOCS, AWAIT_UPLOAD)


def pending_question(db: Session, conv: WhatsAppConversation):
    """
    What the bot is waiting for an answer to: (text, send options), or None.

    The question as it was asked, with its buttons, so a reminder takes the
    person straight back to where they left off.
    """
    step, lang = conv.bot_step, _lang(db, conv)
    if step == CHOOSE_LANG:
        options = language_options(_campaign_lang(db, conv))
        lines = []
        for code in options:
            line = bot_messages.text(code, "language_prompt")
            if line not in lines:
                lines.append(line)
        return "\n".join(lines), {"buttons": [{"id": f"lang:{c}", "title": LANGUAGE_NAMES[c]} for c in options]}
    if step == AWAIT_PIN:
        return _t(db, conv, "bad_pin"), {}
    if step == AWAIT_EDUCATION:
        return _t(db, conv, "ask_education"), {"buttons": education_buttons(lang)}
    if step == AWAIT_FRANCHISE:
        return _t(db, conv, "ask_franchise"), {"buttons": YES_NO("franchise", lang)}
    if step == AWAIT_INVEST:
        return _t(db, conv, "ask_invest"), {"buttons": YES_NO("invest", lang)}
    if step == AWAIT_DOCS:
        return _t(db, conv, "ask_docs", documents=document_list(lang)), {"buttons": YES_NO("docs", lang)}
    if step == AWAIT_UPLOAD and conv.upload_token:
        return _t(db, conv, "remind_upload"), {"link": {"text": _t(db, conv, "link_button"), "url": upload_url(conv)}}
    if step in (GUIDANCE_QA, AWAIT_WEBINAR, AWAIT_AVAILABILITY):
        return _t(db, conv, "guidance_open"), {"buttons": _interested_button()}
    return None


def documents_submitted(db: Session, conv: WhatsAppConversation) -> WhatsAppMessage:
    """The upload page was submitted: thank the person in the chat."""
    from src.services import followups

    conv.documents_submitted_at = inbox.now()
    _move(conv, SUBMITTED)
    # AutoGMap's part is done: the lead goes to Eko Acquisition (Physical visit required).
    followups.hand_over(db, conv, "bot")
    return _say(db, conv, _t(db, conv, "thanks"))


def transcribe_voice(db: Session, conv: WhatsAppConversation, msg: WhatsAppMessage) -> None:
    """
    Write a voice note out as text, once, into its payload.

    Done for every voice note, whoever sent it, so the inbox can show what
    was said; the bot then answers campaign people from the text. A failure
    is recorded rather than raised: the note is still there to listen to.
    """
    payload = dict(msg.payload or {})
    if msg.kind != "audio" or payload.get("transcript") or payload.get("transcript_error"):
        return
    try:
        if not payload.get("stored"):
            inbox.fetch_media(msg)
            payload = dict(msg.payload or {})
        path = payload.get("stored")
        if not path:
            raise RuntimeError(payload.get("fetch_error") or "the voice note could not be downloaded")
        from src.services import transcribe

        heard = transcribe.transcribe(path, fallback_language=_lang(db, conv))
        payload.update(transcript=heard["text"] or None, language=heard["language"],
                       language_probability=heard["probability"])
        if not heard["text"]:
            payload["transcript_error"] = "Nothing could be made out"
    except Exception as exc:
        logger.exception(f"onboarding_bot event=TRANSCRIBE_FAILED message_id={msg.message_id}")
        payload["transcript_error"] = str(exc)[:300]
    msg.payload = payload
    db.commit()


# One email per conversation in this long, unless the reason changes: someone
# sending three questions in a row is one email, not three.
ATTENTION_EMAIL_GAP = timedelta(minutes=10)


def email_attention(db: Session, conv: WhatsAppConversation) -> bool:
    """Email the admin that the bot left this conversation for a person, with its summary."""
    from src.services import auth_service, chat_summary, notifier

    data = conv.bot_data or {}
    last = data.get("attention_emailed") or {}
    if (last.get("reason") == conv.attention_reason and last.get("at")
            and inbox.now() - datetime.fromisoformat(last["at"]) < ATTENTION_EMAIL_GAP):
        return False
    try:
        summary = chat_summary.summarise(db, conv)
        base = (os.environ.get("APP_PUBLIC_URL") or os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
        sent = notifier.notify_attention(auth_service.BOOTSTRAP_ADMIN, summary, chat_summary.as_text(summary),
                                         f"{base}/#inbox/{conv.phone.lstrip('+')}" if base else "the Inbox in AutoGMap")
    except Exception:
        logger.exception(f"onboarding_bot event=ATTENTION_EMAIL_FAILED phone={conv.phone}")
        return False
    if sent:
        conv.bot_data = {**(conv.bot_data or {}),
                         "attention_emailed": {"reason": conv.attention_reason, "at": inbox.now().isoformat()}}
        db.commit()
    logger.info(f"onboarding_bot event=ATTENTION_EMAIL sent={sent} phone={conv.phone}")
    return sent


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
                transcribe_voice(db, conv, msg)
                handle(db, conv, msg)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(f"onboarding_bot event=HANDLE_FAILED message_id={message_id}")
    finally:
        db.close()
