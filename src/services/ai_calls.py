"""
Calls made by the AI calling agent (Voxomos), as it sends them back.

Voxomos posts each finished call to our webhook: who was called, how it went,
and the chat of the call turn by turn (what the agent said, what the
candidate replied, and so on). Here that is stored in full, and AutoGMap
marks the call's outcome as one of the team's dispositions (the user,
2026-11-05), which then sets the next step going like any other disposition:
a WhatsApp nudge, a callback at the time they gave, a ticket for the team.

How the outcome is marked, first match wins:
  1. The outcome Voxomos sends, when it names one of our dispositions (its
     key or its label, as the use-case brief lists them).
  2. A call nobody answered: "No answer", "Busy" or "Number not reachable".
  3. The candidate's own words, read by the same fixed rules the bot uses on
     WhatsApp replies (reply_dispositions), latest statement first: "shaam 5
     baje call karna" is a callback at 5 PM, "galti se apply ho gaya" is
     "Applied by mistake". Asking for existing Kiosk Operators' contacts is a
     trust concern.
  4. Otherwise the chat's outcome stands as it was, and the call says so.

No language model reads the call: the words stay on our server, and the same
call always gives the same outcome.
"""
import hmac
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.models.inbox import AICall, WhatsAppConversation
from src.services import dispositions as dz, handover, inbox, reply_dispositions

logger = logging.getLogger("gmap_scraper.ai_calls")

BY = "ai_call"
PROVIDER = "voxomos"

_AGENT = {"agent", "assistant", "bot", "ai", "voxomos", "caller_agent", "system_agent"}
_CANDIDATE = {"user", "customer", "candidate", "human", "lead", "callee", "client", "person"}
_LINE = re.compile(r"^\s*(agent|assistant|bot|ai|user|customer|candidate|human|lead)\s*[:\-]\s*(.+)$", re.I)

# How a call that never connected is marked, by the status Voxomos sends.
_NOT_CONNECTED = {
    "no_answer": "rnr_no_answer", "no-answer": "rnr_no_answer", "not_answered": "rnr_no_answer",
    "unanswered": "rnr_no_answer", "missed": "rnr_no_answer", "ringing": "rnr_not_picked",
    "busy": "busy_busy", "failed": "unr_not_reachable", "unreachable": "unr_not_reachable",
    "switched_off": "unr_switched_off", "not_reachable": "unr_not_reachable",
}

# Asking for our Kiosk Operators' contacts, to check we are genuine (the use-case brief).
_WANTS_OPERATORS = ("operator ka number", "operators ka number", "operator ke number", "kiosk operator",
                    "csp wale ka number", "kisi operator se baat", "unka number bhejo", "contact bhejo",
                    "operator details", "existing csp", "aapke operator", "operator no", "operator nu number")


def secret_ok(given: Optional[str]) -> bool:
    """The webhook's shared secret; with none set, every call is refused."""
    from src.config import settings
    expected = settings.voxomos_webhook_secret or ""
    return bool(expected) and hmac.compare_digest(expected, given or "")


def _speaker(raw: Optional[str]) -> str:
    s = (raw or "").strip().lower()
    if s in _AGENT:
        return "agent"
    if s in _CANDIDATE:
        return "candidate"
    return "agent" if "agent" in s or "bot" in s else "candidate"


def parse_turns(transcript) -> List[dict]:
    """
    The call's chat as [{"speaker": "agent" | "candidate", "text", "at"}],
    from a list of turns (any of role/speaker and text/message/content) or
    from plain text with one "Agent: ..." / "User: ..." line per turn.
    """
    turns: List[dict] = []
    if isinstance(transcript, str):
        for line in transcript.splitlines():
            m = _LINE.match(line)
            if m:
                turns.append({"speaker": _speaker(m.group(1)), "text": m.group(2).strip(), "at": None})
            elif line.strip() and turns:
                turns[-1]["text"] += " " + line.strip()
        return turns
    for t in transcript or []:
        if not isinstance(t, dict):
            continue
        text = (t.get("text") or t.get("message") or t.get("content") or "").strip()
        if not text:
            continue
        at = t.get("at") or t.get("time") or t.get("timestamp")
        turns.append({"speaker": _speaker(t.get("speaker") or t.get("role") or t.get("from")),
                      "text": text[:2000], "at": str(at) if at is not None else None})
    return turns


def _named_disposition(outcome: Optional[str]) -> Optional[str]:
    """A disposition Voxomos named, by its key or its label."""
    o = (outcome or "").strip()
    if not o:
        return None
    key = dz.normalise(o)
    if key in handover.DISPOSITIONS:
        return key
    low = o.lower()
    for opt in dz.options():
        if (opt.get("label") or "").lower() == low:
            return opt["key"]
    if "kiosk operator" in low and "trust" in low:
        return "int_trust"
    return None


def mark_outcome(status: str, turns: List[dict], provider_outcome: Optional[str],
                 now: datetime) -> Tuple[Optional[str], Optional[datetime], str]:
    """(disposition, time or date it carries, why) for a call; None when the call settles nothing."""
    named = _named_disposition(provider_outcome)
    if named:
        return named, None, f"Voxomos marked it “{provider_outcome}”"
    said = [t["text"] for t in turns if t["speaker"] == "candidate"]
    if not said:
        key = _NOT_CONNECTED.get((status or "").lower(), "rnr_no_answer")
        return key, None, "Nobody spoke on the call" if status == "answered" else f"Call status: {status}"
    for text in reversed(said):
        low = text.lower()
        if any(p in low for p in _WANTS_OPERATORS):
            return "int_trust", None, f"Asked for our Kiosk Operators' contacts: “{text[:120]}”"
        found = reply_dispositions.detect(text, now)
        if found:
            key, when = found
            return key, when, f"They said: “{text[:160]}”"
    return None, None, "No clear outcome in their words; the chat's outcome stays as it was"


def _summary(turns: List[dict], reason: str) -> str:
    said = [t["text"] for t in turns if t["speaker"] == "candidate"]
    return f"{len(turns)} turns, {len(said)} from the candidate. {reason}."


def receive(db: Session, payload: dict, now: Optional[datetime] = None) -> AICall:
    """Stores a finished call, marks its outcome and records it on the chat."""
    now = now or inbox.now()
    phone = inbox.normalize_phone(payload.get("phone") or payload.get("to") or payload.get("customer_number"))
    if not phone:
        raise ValueError("The call has no phone number")
    external = str(payload.get("call_id") or payload.get("id") or "") or None
    call = db.query(AICall).filter(AICall.external_id == external).first() if external else None
    if call is None:
        call = AICall(call_id=uuid.uuid4().hex, external_id=external, provider=PROVIDER, phone=phone, turns=[])
        db.add(call)
    call.phone = phone
    call.status = (payload.get("status") or "answered").strip().lower()[:20]
    call.turns = parse_turns(payload.get("transcript") or payload.get("turns") or payload.get("conversation"))
    call.duration_seconds = int(payload["duration"]) if str(payload.get("duration", "")).isdigit() else call.duration_seconds
    started = payload.get("started_at") or payload.get("start_time")
    try:
        call.started_at = inbox.aware(datetime.fromisoformat(str(started).replace("Z", "+00:00"))) if started else now
    except ValueError:
        call.started_at = now
    call.language = (payload.get("language") or None)
    call.recording_url = (payload.get("recording_url") or None)
    call.provider_outcome = (str(payload.get("outcome") or payload.get("disposition") or "")[:200] or None)

    key, when, reason = mark_outcome(call.status, call.turns, call.provider_outcome, now)
    # What the call showed, shown on its card even when the chat keeps another outcome.
    shown = key
    conv = db.get(WhatsAppConversation, phone)
    if key and conv is not None:
        if conv.documents_submitted_at and key != "int_visit":
            # Documents are in: the chat belongs to Eko Acquisition now.
            reason += "; documents already in, so nothing was changed"
            key = None
        else:
            handover.record(db, conv, key, by=BY, note=f"AI call: {reason}"[:500], at=when)
    elif key and conv is None:
        reason += "; no WhatsApp chat with this number, so it is only stored here"
    call.outcome = shown
    call.outcome_reason = reason[:300]
    call.outcome_at = now
    call.summary = _summary(call.turns, reason)
    db.commit()
    logger.info(f"ai_call event=RECEIVED call={call.call_id} status={call.status} outcome={call.outcome} "
                f"turns={len(call.turns)}")
    return call


def as_dict(c: AICall) -> dict:
    return {
        "call_id": c.call_id, "phone": c.phone, "provider": c.provider, "status": c.status,
        "started_at": inbox.aware(c.started_at).isoformat() if c.started_at else None,
        "duration_seconds": c.duration_seconds, "language": c.language, "recording_url": c.recording_url,
        "turns": c.turns or [], "provider_outcome": c.provider_outcome,
        "outcome": c.outcome, "outcome_label": dz.label(c.outcome) if c.outcome else None,
        "outcome_group": (dz.category_of(c.outcome).group if c.outcome and dz.category_of(c.outcome) else None),
        "outcome_reason": c.outcome_reason, "summary": c.summary,
    }


def for_phone(db: Session, phone: str) -> List[dict]:
    rows = (db.query(AICall).filter(AICall.phone == inbox.normalize_phone(phone))
            .order_by(AICall.started_at.desc()).all())
    return [as_dict(c) for c in rows]
