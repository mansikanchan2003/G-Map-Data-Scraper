"""
Which programme a candidate chose on a call: SBI's CSP or ESAF's banking agent (18 Nov 2026).

When someone is called from our end (by Kavya Ma'am, from her phone's call recorder, or by
the AI calling agent), the chat's disposition follows what was said: a person in the SBI
flow who says on the call they want ESAF becomes "Interested in ESAF", and the other way
round becomes "Interested in SBI" (handover.PROGRAMME_DISPOSITIONS moves their documents too).

Fixed rules on their words, like reply_dispositions: no language model reads the call, and
the same words always give the same answer. A statement counts when it names one programme
with a sign of wanting it ("ESAF karna hai", "SBI wala chahiye", "interested in ESAF"), or
turns one down for the other ("SBI nahi, ESAF"). Questions do not count ("ESAF kya hai?").
The latest such statement wins.

A recording has no speakers, and the caller explains both programmes, so there only
statements in the first person ("mujhe ESAF karna hai", "main SBI wala lunga") count.
"""
import re
from typing import Iterable, Optional, Tuple

ESAF = ("esaf", "e saf", "e-saf", "isaf", "ईसाफ", "इसाफ", "ઈસાફ", "1999 wala", "1999 vala", "1,999 wala")
SBI = ("sbi", "s b i", "state bank", "एसबीआई", "स्टेट बैंक", "એસબીઆઈ")

WANT = ("karna hai", "karna h", "karni hai", "karunga", "karungi", "karenge", "chahiye", "chahta", "chahti",
        "lena hai", "lunga", "lungi", "lenge", "interested", "interest hai", "join", "register", "apply",
        "wala hi", "vala hi", "better hai", "theek hai", "thik hai", "sahi hai", "ok hai", "haan", "ha ji",
        "want", "go with", "prefer", "would like", "करना है", "करूंगा", "करूँगा", "चाहिए", "लूंगा", "ठीक है",
        "हां", "हाँ")
# Not "mein": it is also "in" ("aap ESAF mein interested hain" is the caller asking).
FIRST_PERSON = ("mujhe", "muje", "mujhko", "main ", "mai ", "hum ", "humko", "hame", "hamein", "mera",
                "meri", "i ", "i'm", "i am", "i want", "i will", "मुझे", "मैं", "हम", "हमें", "मेरा", "મને", "હું")

_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n+")


def _norm(text: str) -> str:
    return " " + re.sub(r"\s+", " ", (text or "").lower()).strip() + " "


def _has(t: str, words: Iterable[str]) -> bool:
    return any(w in t for w in words)


# Whole words only: "dono" (both) is not "no".
_NOT_AFTER = re.compile(r"^\W*(?:\w+\W+)?(nahi|nhi|nahin|mat|no|not|don'?t|नहीं|नही|ના|નહીં)(?!\w)")
_NOT_BEFORE = re.compile(r"(?<!\w)(not|no|नहीं)\W*$")


def _negated(t: str, words: Iterable[str]) -> bool:
    """A programme named and turned down in the next word or two: "sbi nahi", "esaf wala nahi", "not sbi"."""
    for w in words:
        i = t.find(w)
        while i != -1:
            after, before = t[i + len(w): i + len(w) + 20], t[max(0, i - 8): i]
            if _NOT_AFTER.search(after) or _NOT_BEFORE.search(before):
                return True
            i = t.find(w, i + 1)
    return False


def statement(text: str, first_person: bool = False) -> Optional[str]:
    """"esaf", "sbi" or None for one statement."""
    t = _norm(text)
    if "?" in t or (first_person and not _has(t, FIRST_PERSON)):
        return None
    esaf, sbi = _has(t, ESAF), _has(t, SBI)
    if esaf and sbi:
        if _negated(t, SBI) and not _negated(t, ESAF):
            return "esaf"
        if _negated(t, ESAF) and not _negated(t, SBI):
            return "sbi"
        return None
    if esaf and not _negated(t, ESAF) and _has(t, WANT):
        return "esaf"
    if sbi and not _negated(t, SBI) and _has(t, WANT):
        return "sbi"
    return None


def chosen(texts: Iterable[str], first_person: bool = False) -> Optional[Tuple[str, str]]:
    """(programme, the words that said so) from a call's statements, the latest first; None when none says."""
    parts = [p for text in texts for p in _SPLIT.split(text or "") if p.strip()]
    for part in reversed(parts):
        found = statement(part, first_person)
        if found:
            return found, part.strip()
    return None


LABEL = {"esaf": "ESAF", "sbi": "SBI"}


def apply(db, conv, found: Optional[Tuple[str, str]], by: str, how: str) -> Optional[str]:
    """
    The disposition recorded when the call moved them to the other programme; None when it
    did not (nothing said, or the programme they are already in). `how` names the call.
    """
    from src.services import handover
    if not found or conv is None:
        return None
    wanted, words = found
    if wanted == handover.programme(conv):
        return None
    key = "int_esaf" if wanted == "esaf" else "int_sbi"
    handover.record(db, conv, key, by=by, note=f"{how}: chose {LABEL[wanted]} (“{words[:160]}”)"[:500])
    return key
