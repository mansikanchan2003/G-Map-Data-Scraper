"""
The disposition a lead's own reply stands for, read by fixed rules (the
user's sheet, 2026-10-23: "Bot" records these). No language model: the same
words always give the same disposition, so the bot stays predictable.

"Abhi busy hoon, shaam 5 baje call karna" is "Call at specific time" at 5 PM;
"galti se apply ho gaya" is "Applied by mistake"; "yeh mera number nahi hai"
is "Incorrect customer details". The bot records it, and the disposition's
follow-ups and closing message do the rest (dispositions.py).

Read only from a message that is not an answer to the bot's own question and
not a question of theirs (onboarding_bot decides that), so "nahi" to "can you
invest?" is still a No there, and "kya baad mein apply kar sakte hain?" is a
question for the FAQ, not "Interested later".

The phrases cover English, Hinglish, Hindi and Gujarati, the languages most
leads write in; matching is on whole phrases, after lower-casing.
"""
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple

IST = timezone(timedelta(hours=5, minutes=30))

# (disposition, phrases), checked in this order: the first that matches wins.
RULES: List[Tuple[str, Tuple[str, ...]]] = [
    ("inv_denied", ("maine apply nahi kiya", "maine apply nhi kiya", "mene apply nahi kiya", "i did not apply",
                    "i didn't apply", "i have not applied", "never applied", "apply nahi kiya tha",
                    "मैंने अप्लाई नहीं", "मैंने आवेदन नहीं", "મેં અરજી નથી કરી", "મેં એપ્લાય નથી કર્યું")),
    ("inv_incorrect", ("wrong number", "galat number", "galat no", "not my number", "mera number nahi",
                       "yeh mera nahi", "ye mera nahi", "wrong person", "गलत नंबर", "मेरा नंबर नहीं",
                       "ખોટો નંબર", "મારો નંબર નથી")),
    ("dup_existing", ("already csp", "already a csp", "already have a csp", "already running a csp",
                      "already have csp", "pehle se csp", "pahle se csp", "already kiosk", "pehle se kiosk",
                      "pahle se kiosk", "existing csp", "already bc", "pehle se bc", "already working with eko",
                      "pehle se eko", "पहले से csp", "पहले से कियोस्क", "पहले से ही csp", "પહેલેથી csp",
                      "પહેલેથી કિઓસ્ક")),
    ("dup_in_process", ("already applied", "pehle hi apply", "pehle se apply", "pahle hi apply",
                        "apply kar diya hai", "apply kar chuka", "apply kar chuki", "already in process",
                        "process chal raha", "पहले ही अप्लाई", "पहले ही आवेदन", "आवेदन कर दिया",
                        "પહેલેથી અરજી", "અરજી કરી દીધી")),
    ("ndm_not_applicant", ("not the applicant", "i am not the applicant", "main applicant nahi",
                           "mai applicant nahi", "papa ka number", "pitaji ka number", "bhai ka number",
                           "pati ka number", "husband ka number", "father's number", "father ka number",
                           "beta ka number", "bete ka number", "पापा का नंबर", "भाई का नंबर", "पति का नंबर",
                           "પપ્પાનો નંબર", "ભાઈનો નંબર")),
    ("ndm_unavailable", ("ghar par nahi", "ghar pe nahi", "ghar nahi hai", "bahar gaye", "bahar gaya",
                         "out of station", "is not available", "are not available", "abhi available nahi",
                         "घर पर नहीं", "बाहर गए", "ઘરે નથી", "બહાર ગયા")),
    ("ni_mistake", ("by mistake", "galti se", "galati se", "mistake se", "accidentally", "गलती से",
                    "भूल से", "ભૂલથી")),
    ("rej_credit", ("cibil", "credit score", "loan default", "defaulter", "सिबिल", "क्रेडिट स्कोर")),
    ("hold_financial", ("paise nahi", "paisa nahi", "paise nhi", "no money", "don't have money",
                        "funds nahi", "financial problem", "financial issue", "paison ki dikkat",
                        "पैसे नहीं", "पैसा नहीं", "पैसों की", "પૈસા નથી")),
    ("hold_later", ("next month", "agle mahine", "agle mahina", "after diwali", "diwali ke baad",
                    "baad mein karunga", "baad me karunga", "baad mein karungi", "baad me karungi",
                    "baad mein dekhenge", "baad me dekhenge", "kuch din baad", "few days later",
                    "after some days", "after exam", "next year", "agle saal", "agle hafte", "next week",
                    "अगले महीने", "अगले हफ्ते", "बाद में करूंगा", "बाद में करूँगा", "बाद में देखेंगे",
                    "दिवाली के बाद", "આવતા મહિને", "આવતા અઠવાડિયે", "પછી કરીશ", "દિવાળી પછી")),
    ("ni_no_requirement", ("no need", "zarurat nahi", "zaroorat nahi", "jarurat nahi", "jaroorat nahi",
                           "nahi chahiye", "nhi chahiye", "don't want", "do not want", "not required",
                           "no requirement", "जरूरत नहीं", "ज़रूरत नहीं", "नहीं चाहिए", "જરૂર નથી",
                           "નથી જોઈતું")),
    ("ni_currently", ("not interested", "interested nahi", "interested nhi", "interest nahi",
                      "intrested nahi", "abhi nahi", "not now", "रुचि नहीं", "इंटरेस्टेड नहीं",
                      "इंटरेस्ट नहीं", "રસ નથી", "હમણાં નહીં")),
    ("busy_at_time", ()),   # a time with a call or busy word: see detect()
    ("busy_later", ("call later", "baad mein call", "baad me call", "baad mein baat", "baad me baat",
                    "later call", "talk later", "बाद में कॉल", "बाद में बात", "પછી ફોન", "પછી વાત")),
    ("int_callback", ("call me", "call karo", "call kariye", "call kijiye", "call karna", "call kar do",
                      "phone karo", "phone kijiye", "phone karna", "call back", "callback", "mujhe call",
                      "कॉल करें", "कॉल करो", "कॉल कीजिए", "फोन करो", "फोन करें", "ફોન કરો", "કોલ કરો")),
    ("busy_busy", ("busy", "vyast", "meeting mein", "meeting me", "driving", "व्यस्त", "बिजी", "વ્યસ્ત",
                   "બિઝી")),
    ("lang_barrier", ("samajh nahi aaya", "samajh nahi aa raha", "samajh nhi aaya", "samjh nahi",
                      "english nahi aati", "english nahi aata", "hindi nahi aati", "hindi nahi aata",
                      "don't understand", "do not understand", "समझ नहीं", "हिंदी नहीं आती",
                      "अंग्रेजी नहीं आती", "સમજ નથી પડતી", "સમજાયું નહીં")),
]

_CALL_OR_BUSY = ("call", "phone", "baat", "busy", "कॉल", "फोन", "बात", "ફોન", "કોલ", "વાત")
_TIME = re.compile(r"(?<!\d)(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.|baje|bje|बजे|વાગ્યે|vage|vaage)",
                   re.I)
_EVENING = ("shaam", "sham", "evening", "night", "raat", "शाम", "रात", "સાંજે", "રાત્રે", "pm", "p.m.")
_MORNING = ("subah", "morning", "सुबह", "સવારે", "am", "a.m.")
_TOMORROW = ("kal", "tomorrow", "कल", "આવતીકાલે", "kale")
_DAY_AFTER = ("parso", "day after tomorrow", "परसों", "પરમદિવસે")
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_DATE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:st|nd|rd|th)?\s*(" + "|".join(_MONTHS) + r")[a-z]*", re.I)
_IN_DAYS = re.compile(r"(?<!\d)(\d{1,2})\s*(din|days|day|दिन|દિવસ)", re.I)
_IN_MONTHS = re.compile(r"(?<!\d)(\d{1,2})\s*(mahine|mahina|months|month|महीने|મહિના)", re.I)


def _has(text: str, phrase: str) -> bool:
    """A phrase as whole words (Latin) or as written (Indian scripts)."""
    if phrase.isascii():
        return re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", text) is not None
    return phrase in text


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("’", "'").split())


def call_time(text: str, now: datetime) -> Optional[datetime]:
    """The time they asked to be called at ("5 baje", "kal 11 am", "shaam 6 baje"), in UTC."""
    t = _norm(text)
    m = _TIME.search(t)
    if not m:
        return None
    hour, minute, mark = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
    if hour > 23 or minute > 59:
        return None
    evening = mark in ("pm", "p.m.") or any(_has(t, w) for w in _EVENING if w not in ("pm", "p.m."))
    morning = mark in ("am", "a.m.") or any(_has(t, w) for w in _MORNING if w not in ("am", "a.m."))
    if hour < 12 and evening:
        hour += 12
    elif hour < 8 and not morning:
        hour += 12      # "5 baje" means 5 in the evening, as people say it
    local = now.astimezone(IST)
    day = local.date()
    if any(_has(t, w) for w in _DAY_AFTER):
        day += timedelta(days=2)
    elif any(_has(t, w) for w in _TOMORROW):
        day += timedelta(days=1)
    at = datetime.combine(day, time(hour, minute), tzinfo=IST)
    if at <= local:
        at += timedelta(days=1)
    return at.astimezone(timezone.utc)


def follow_up_date(text: str, now: datetime) -> Optional[datetime]:
    """The day to check back on ("next month", "15 November", "10 din baad"), in UTC; None if not said."""
    t = _norm(text)
    today = now.astimezone(IST).date()
    day: Optional[date] = None
    m = _DATE.search(t)
    if m:
        month = _MONTHS.index(m.group(2).lower()[:3]) + 1
        try:
            day = date(today.year, month, int(m.group(1)))
        except ValueError:
            day = None
        if day and day <= today:
            day = date(today.year + 1, month, day.day)
    elif _IN_DAYS.search(t):
        day = today + timedelta(days=int(_IN_DAYS.search(t).group(1)))
    elif _IN_MONTHS.search(t):
        day = today + timedelta(days=30 * int(_IN_MONTHS.search(t).group(1)))
    elif any(_has(t, w) for w in ("next week", "agle hafte", "अगले हफ्ते", "આવતા અઠવાડિયે")):
        day = today + timedelta(days=7)
    elif any(_has(t, w) for w in ("next month", "agle mahine", "agle mahina", "अगले महीने", "આવતા મહિને")):
        day = today + timedelta(days=30)
    elif any(_has(t, w) for w in ("next year", "agle saal")):
        day = today + timedelta(days=365)
    if day is None:
        return None
    return datetime.combine(day, time(11, 0), tzinfo=IST).astimezone(timezone.utc)


def detect(text: Optional[str], now: Optional[datetime] = None) -> Optional[Tuple[str, Optional[datetime]]]:
    """
    (disposition, when) for what they wrote, or None. `when` is the time to
    call back, or the date to check back on, where they said one.
    """
    t = _norm(text)
    if not t:
        return None
    now = now or datetime.now(timezone.utc)
    for key, phrases in RULES:
        if key == "busy_at_time":
            at = call_time(t, now)
            if at and any(_has(t, w) for w in _CALL_OR_BUSY):
                return key, at
            continue
        if any(_has(t, p) for p in phrases):
            if key == "hold_later":
                when = follow_up_date(t, now)
                # A date of their own is "Wants to proceed after certain date".
                return ("hold_after_date" if when and _DATE.search(t) else key), when
            if key == "hold_financial":
                return key, follow_up_date(t, now)
            return key, None
    return None


def matched_phrase(text: Optional[str], key: str) -> Optional[str]:
    """The phrase in their words that made it this disposition: the "why", for the Agent quality page."""
    t = _norm(text)
    if key == "busy_at_time":
        m = _TIME.search(t)
        return m.group(0) if m else None
    rule = "hold_later" if key == "hold_after_date" else key
    for k, phrases in RULES:
        if k == rule:
            return next((p for p in phrases if _has(t, p)), None)
    return None
