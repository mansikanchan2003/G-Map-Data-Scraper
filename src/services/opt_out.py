"""
Numbers that must not be messaged again (DPDP; WhatsApp's Business Policy).

A number goes on the list when:
- the person says so in the chat ("stop", "message mat bhejo", ...);
- the chat is closed as not interested, applied by mistake, denied applying,
  or not the applicant (OPT_OUT_DISPOSITIONS);
- WhatsApp reports they have stopped marketing messages (error 131050);
- the team puts it there from the Inbox.

On the list, no campaign is sent to it (the recipient is skipped, whatever
the audience or sheet), the bot sends no reminder, and its follow-ups stop.
The bot still answers when they write to us themselves. A disposition's own
closing message still goes: the opt-out only stops what would come after.

It comes off when they ask again (START, or tapping a campaign button), or
when the team takes it off.
"""
import logging
import re
from typing import Optional, Set

from sqlalchemy.orm import Session

from src.models.opt_out import OptOut

logger = logging.getLogger("gmap_scraper.opt_out")

SAID_STOP, DISPOSITION, META, TEAM = "said_stop", "disposition", "meta", "team"
SOURCES = {
    SAID_STOP: "Asked in the chat not to be messaged",
    DISPOSITION: "Closed as not interested",
    META: "Stopped marketing messages on WhatsApp",
    TEAM: "Put on the list by the team",
}

# Chats closed this way are not marketed to again. Investment issue and the
# "hold" ones are left out: the team still follows those up.
OPT_OUT_DISPOSITIONS = {"ni_mistake", "ni_no_requirement", "ni_currently", "inv_denied", "ndm_not_applicant"}
# WhatsApp: "This user has chosen to stop receiving marketing messages".
META_STOPPED_CODE = "131050"

# Short messages only: "stop" in a sentence ("bus stop ke paas") is not a request.
_STOP = re.compile(
    r"^\s*(?:pl(?:ea)?se?\s+|plz\s+)?(?:"
    r"stop|unsubscribe|opt\s*out|"
    r"(?:do\s*n[o']?t|dont|no\s+more|stop)\s+(?:send(?:ing)?\s+)?(?:any\s+)?(?:more\s+)?(?:messages?|msgs?|texts?)(?:\s+(?:to\s+)?me)?|"
    r"(?:mujhe\s+)?(?:message|msg|messages|sms)\s+(?:mat|na|nahi|nhi)\s+(?:bhej(?:o|e|ein|en|iye|na)?|karo|kare|karein)|"
    r"(?:message|msg|messages)\s+(?:bhejna\s+)?band\s+(?:karo|kare|karein|kar\s+do|kardo)|"
    r"bhejna\s+band\s+(?:karo|kare|karein|kar\s+do|kardo)|"
    r"मत\s+भेजो|मैसेज\s+मत\s+भेजो|मेसेज\s+मत\s+भेजो|मैसेज\s+बंद\s+करो|मेसेज\s+बंद\s+करो|भेजना\s+बंद\s+करो|"
    r"ના\s+મોકલો|મેસેજ\s+ના\s+મોકલો|મેસેજ\s+બંધ\s+કરો|મોકલવાનું\s+બંધ\s+કરો|"
    r"ਨਾ\s+ਭੇਜੋ|ਮੈਸੇਜ\s+ਨਾ\s+ਭੇਜੋ|ਮੈਸੇਜ\s+ਬੰਦ\s+ਕਰੋ"
    r")\s*[.!।]*\s*$",
    re.IGNORECASE,
)
_START = re.compile(r"^\s*(?:start|subscribe|resume)\s*[.!]*\s*$", re.IGNORECASE)


def says_stop(text: Optional[str]) -> bool:
    return bool(text) and bool(_STOP.match(text))


def says_start(text: Optional[str]) -> bool:
    return bool(text) and bool(_START.match(text))


def entry(db: Session, phone: str) -> Optional[OptOut]:
    return db.get(OptOut, phone) if phone else None


def is_out(db: Session, phone: str) -> bool:
    return entry(db, phone) is not None


def phones(db: Session) -> Set[str]:
    return {p for (p,) in db.query(OptOut.phone).all()}


def blocks_followups(e: Optional[OptOut]) -> bool:
    """A disposition's own closing message still goes; any other opt-out stops follow-ups."""
    return e is not None and e.source != DISPOSITION


def record(db: Session, phone: str, source: str, by: str, reason: Optional[str] = None) -> OptOut:
    """Put the number on the list (once; the first reason is kept). The caller commits."""
    e = entry(db, phone)
    if e is None:
        e = OptOut(phone=phone, source=source, created_by=by, reason=(reason or SOURCES.get(source, ""))[:300])
        db.add(e)
        db.flush()
        logger.info(f"opt_out event=ADDED phone=...{phone[-4:]} source={source} by={by}")
        if source != DISPOSITION:
            from src.services import followups
            followups._cancel(db, phone, "Asked not to be messaged", tasks_too=False)
    return e


def remove(db: Session, phone: str, by: str, why: str) -> bool:
    """Take the number off the list. The caller commits."""
    e = entry(db, phone)
    if e is None:
        return False
    db.delete(e)
    db.flush()
    logger.info(f"opt_out event=REMOVED phone=...{phone[-4:]} by={by} why={why}")
    return True


def as_dict(e: Optional[OptOut]) -> Optional[dict]:
    if e is None:
        return None
    from src.services.inbox import aware
    return {"source": e.source, "label": SOURCES.get(e.source, e.source), "reason": e.reason,
            "by": e.created_by, "at": aware(e.created_at).isoformat() if e.created_at else None}
