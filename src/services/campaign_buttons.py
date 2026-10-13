"""
The quick-reply buttons every generated template carries.

They are fixed rather than written by the agent, because the onboarding bot
answers a tap by its label: a button the agent re-worded would reach nobody.
"Interested" starts onboarding and stays in English everywhere; the webinar
button is in the template's own language, and the bot knows every version.
"""
import unicodedata
from typing import Optional

INTERESTED = "Interested"

# "Webinar Chahiye" in each language a template can be written in. Each is
# within Meta's 20-character limit for a button.
WEBINAR = {
    "en": "Webinar Chahiye",
    "hi": "वेबिनार चाहिए",
    "mr": "वेबिनार हवा आहे",
    "pa": "ਵੈਬੀਨਾਰ ਚਾਹੀਦਾ ਹੈ",
    "gu": "વેબિનાર જોઈએ",
    "bn": "ওয়েবিনার চাই",
    "ta": "வெபினார் வேண்டும்",
    "te": "వెబినార్ కావాలి",
    "kn": "ವೆಬಿನಾರ್ ಬೇಕು",
    "ml": "വെബിനാർ വേണം",
    "or": "ୱେବିନାର ଦରକାର",
}


def webinar_label(language_code: Optional[str]) -> str:
    return WEBINAR.get((language_code or "").split("_")[0], WEBINAR["en"])


def quick_replies(language_code: Optional[str]) -> list:
    return [
        {"type": "QUICK_REPLY", "text": INTERESTED},
        {"type": "QUICK_REPLY", "text": webinar_label(language_code)},
    ]


def key(text: Optional[str]) -> str:
    """
    A label reduced to its letters, so "Interested?" matches "Interested".

    Indic vowel signs are combining marks rather than letters, and dropping
    them would make different words look alike, so they are kept.
    """
    return "".join(ch for ch in (text or "").lower()
                   if ch.isalnum() or unicodedata.category(ch).startswith("M"))


WEBINAR_KEYS = {key(label) for label in WEBINAR.values()}


def is_webinar(text: Optional[str]) -> bool:
    return bool(key(text)) and key(text) in WEBINAR_KEYS
