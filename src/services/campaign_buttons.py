"""
The quick-reply buttons every generated template carries.

They are fixed rather than written by the agent, because the onboarding bot
answers a tap by its label: a button the agent re-worded would reach nobody.
"Interested" starts onboarding and stays in English everywhere; the
personal guidance button is in the template's own language, and the bot
knows every version, the old "Webinar Chahiye" ones included.
"""
import unicodedata
from typing import Optional

INTERESTED = "Interested"

# "Personal Guidance Chahiye" in each language a template can be written in.
# Each is within Meta's 25-character limit for a template's button. (The
# dict keeps its old name: the flow behind it is still called "webinar" in
# the code and the stored conversations.)
WEBINAR = {
    "en": "Personal Guidance Chahiye",
    "hi": "पर्सनल गाइडेंस चाहिए",
    "mr": "पर्सनल गाइडन्स हवे",
    "pa": "ਪਰਸਨਲ ਗਾਈਡੈਂਸ ਚਾਹੀਦੀ",
    "gu": "પર્સનલ ગાઇડન્સ જોઈએ",
    "bn": "পার্সোনাল গাইডেন্স চাই",
    "ta": "பர்சனல் கைடன்ஸ் வேண்டும்",
    "te": "పర్సనల్ గైడెన్స్ కావాలి",
    "kn": "ಪರ್ಸನಲ್ ಗೈಡೆನ್ಸ್ ಬೇಕು",
    "ml": "പേഴ്സണൽ ഗൈഡൻസ് വേണം",
    "or": "ପର୍ସନାଲ ଗାଇଡାନ୍ସ ଦରକାର",
}

# The buttons before it was renamed, still on templates Meta approved then
# and on campaigns already sent: a tap on one starts the same flow.
OLD_WEBINAR = {
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

# A button the bot itself sends may be 20 characters at most.
REPLY_BUTTON_LIMIT = 20


def webinar_label(language_code: Optional[str]) -> str:
    return WEBINAR.get((language_code or "").split("_")[0], WEBINAR["en"])


def webinar_title(language_code: Optional[str]) -> str:
    """The label for a button the bot sends: without "Chahiye" when too long."""
    label = webinar_label(language_code)
    return label if len(label) <= REPLY_BUTTON_LIMIT else label.rsplit(" ", 1)[0]


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


WEBINAR_KEYS = {key(label) for labels in (WEBINAR, OLD_WEBINAR) for label in labels.values()}


def is_webinar(text: Optional[str]) -> bool:
    return bool(key(text)) and key(text) in WEBINAR_KEYS
