"""
The bot coach: Claude reads how the bot's chats went and proposes changes to
the bot (the user, 2026-11-06), which the admin accepts one by one in the
learning loop (Agent quality page). The bot itself never calls a model: once a
change is accepted it is a fixed rule or a fixed message, so the bot stays
deterministic, and every change can be undone.

What Claude proposes:
  - nudge_timing:  how long after the bot's unanswered question its reminder
                   goes, per question (1 to 23 hours: it must go while their
                   24-hour WhatsApp window is open). Today it is 1 hour.
  - nudge_variant: the same reminder in another shape and words, per purpose
                   and language. The bot then takes turns through the original
                   and the accepted versions, in a fixed order for each person.
  - faq_link:      a question people asked that the bot left for the team,
                   linked to the Eko-confirmed answer that covers it (what
                   "Teach the bot" does by hand). Eko's answers never change.

How it runs: the backend runs in Docker, and Claude runs on the server with
Mansi's own Claude CLI login (her choice, 2026-11-06), outside the app. So a
host script (scripts/run_bot_coach.sh) asks the app for the brief
(`python -m src.services.bot_coach brief`), gives it to `claude -p`, and hands the
answer back (`python -m src.services.bot_coach ingest`). No login or key of hers
is ever inside the app.

What leaves the server: counts, the bot's own message texts, Eko's FAQ, and
the questions people asked with names, numbers and emails taken out.
"""
import hashlib
import json
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

AGENT = "bot_coach"
BY = "Claude (bot coach)"
LOOKBACK_DAYS = 45
MIN_HOURS, MAX_HOURS = 1, 23
MAX_VARIANT_CHARS = 600
# The languages the coach writes versions in; others keep the original only.
VARIANT_LANGS = ("en", "hinglish", "hi", "gu", "mr", "pa")
BUCKETS = [(1, "under 1 h"), (2, "1-2 h"), (4, "2-4 h"), (8, "4-8 h"), (24, "8-24 h")]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


# --- Taking people out of the text --------------------------------------------------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_NUMBER = re.compile(r"\+?\d[\d\s-]{3,}\d")


def redact(text: str, names: List[str]) -> str:
    t = _EMAIL.sub("[email]", text or "")
    t = _NUMBER.sub("[number]", t)
    for n in names:
        for part in (n or "").split():
            if len(part) >= 3:
                t = re.sub(rf"\b{re.escape(part)}\b", "[name]", t, flags=re.IGNORECASE)
    return " ".join(t.split())[:300]


# --- The brief ----------------------------------------------------------------------

def _bucket(hours: float) -> str:
    for limit, label in BUCKETS:
        if hours < limit:
            return label
    return "over 24 h"


def evidence(db: Session) -> dict:
    """What the coach is shown: how the chats went, in counts and the bot's own words."""
    from src.models.inbox import AttentionTicket, FollowUp, WhatsAppConversation, WhatsAppMessage
    from src.services import bot_messages, eko_knowledge, inbox, learning_loop, nudge_messages
    from src.services import onboarding_bot as bot

    since = _now() - timedelta(days=LOOKBACK_DAYS)
    convs = [c for c in db.query(WhatsAppConversation).all()
             if (c.bot_data or {}).get("campaign") and (inbox.aware(c.last_message_at) or since) >= since]
    names = [c.profile_name for c in db.query(WhatsAppConversation.profile_name) if c.profile_name]
    phones = [c.phone for c in convs]

    # How long people take to answer the bot when they do, and how many never do.
    delays, unanswered = Counter(), 0
    if phones:
        msgs = defaultdict(list)
        for m in (db.query(WhatsAppMessage).filter(WhatsAppMessage.phone.in_(phones))
                  .order_by(WhatsAppMessage.created_at).all()):
            msgs[m.phone].append(m)
        for phone, ms in msgs.items():
            asked = None
            for m in ms:
                if m.direction == "OUT" and m.sent_by == "bot":
                    asked = asked or inbox.aware(m.created_at)
                elif m.direction == "IN" and asked:
                    delays[_bucket((inbox.aware(m.created_at) - asked).total_seconds() / 3600)] += 1
                    asked = None
            if asked:
                unanswered += 1

    # The bot's reminders: per question, how many got one and how many answered after it.
    nudged = defaultdict(lambda: {"stopped_here": 0, "nudged": 0, "answered_after_nudge": 0})
    for c in convs:
        step = c.bot_step or "none"
        data = c.bot_data or {}
        row = nudged[step]
        if step in bot.NUDGE_STEPS:
            row["stopped_here"] += 1
        at = data.get("nudged_at")
        if at:
            row["nudged"] += 1
            if inbox.aware(c.last_inbound_at) and inbox.aware(c.last_inbound_at) > datetime.fromisoformat(at):
                row["answered_after_nudge"] += 1

    # The disposition nudges (they stand in for calls): sent, answered, not answered.
    follow = defaultdict(Counter)
    for f in db.query(FollowUp).filter(FollowUp.owner == "bot", FollowUp.created_at >= since).all():
        follow[f"{f.purpose} ({f.language or '?'})"][f.status] += 1

    # Questions the bot left for the team.
    asked = []
    for t in (db.query(AttentionTicket).filter(AttentionTicket.raised_at >= since)
              .order_by(AttentionTicket.raised_at.desc()).limit(200)):
        q = redact(t.latest_question or t.question or "", names)
        if q and q not in asked:
            asked.append(q)
    from src.services import faq_learning
    taught = {q for qs in faq_learning.taught(db).values() for q in qs}

    current = {s: learning_loop.nudge_delay(db, s).total_seconds() / 3600 for s in bot.NUDGE_STEPS}
    opener = {lang: bot_messages.text(lang, "nudge") for lang in ("en", "hi", "gu", "mr", "pa")}
    opener["hinglish"] = bot_messages.HINGLISH.get("nudge", "")
    purposes = {p: {v: nudge_messages.text(p, v) for v in VARIANT_LANGS} for p in nudge_messages.PURPOSES}
    return {
        "window_days": LOOKBACK_DAYS,
        "campaign_chats": len(convs),
        "reply_delay_after_bot_message": dict(delays),
        "bot_messages_never_answered": unanswered,
        "reminder_by_question": {k: v for k, v in nudged.items() if k in bot.NUDGE_STEPS},
        "reminder_hours_now": current,
        "disposition_nudges": {k: dict(v) for k, v in follow.items()},
        "reminder_opener": opener,
        "disposition_nudge_texts": purposes,
        "versions_already_accepted": learning_loop.accepted_variants(db),
        "questions_left_for_team": [q for q in asked if q.lower() not in {x.lower() for x in taught}][:60],
        "eko_answers": [{"id": f["id"], "question": f["question"],
                         "answer": (f.get("answer") or {}).get("en", "")[:220]} for f in eko_knowledge.FAQ],
        "words_never_to_use": [why for _, why in eko_knowledge.AVOID],
    }


INSTRUCTIONS = """You are coaching a WhatsApp bot for Eko (said "Echo"), which helps shop owners in India open an
SBI Customer Service Point (a small SBI banking outlet) and become Kiosk Operators. The bot asks, in order: language,
PIN code, education, whether they can invest Rs 3-5 lakh, then documents. When a person stops answering, it sends one
reminder. The goal of every reminder is to win their trust and get them to send their documents.

The bot must stay predictable, so you do not talk to anyone. You propose changes; a person approves each one, and the
bot then uses it word for word. Propose only what the evidence below supports. Fewer, better proposals beat many.

1. nudge_timing: for a question (its step name), how many hours after the bot's unanswered question the reminder
   should go. Whole hours from 1 to 23 (it must go while the person's 24-hour WhatsApp window is open). Base it on
   reply_delay_after_bot_message and reminder_by_question, and say why in one plain sentence.
2. nudge_variant: the same reminder written another way: same meaning and purpose, different words and shape (a
   question, a short friendly line, a benefit first...). For "bot_nudge" (the reminder opener before the bot repeats
   its question) or for a disposition purpose (a key of disposition_nudge_texts). Language: one of en, hinglish, hi,
   gu, mr, pa, written in that language's own script (hinglish = Hindi in Latin letters). Keep "Eko", "SBI" and rupee
   amounts as they are. Never promise a fixed or guaranteed income, never call it a job or salary, never say zero
   investment, no false urgency, no placeholders like {name}. Under 400 characters. At most 2 per purpose and language.
3. faq_link: a question from questions_left_for_team that one of eko_answers fully answers, with that answer's id.
   Only when the answer really answers it; never invent a new answer.

Answer with JSON only, nothing before or after it:
{"summary": "two plain sentences on what you saw",
 "nudge_timing": [{"step": "...", "hours": 3, "why": "..."}],
 "nudge_variant": [{"purpose": "bot_nudge", "language": "hinglish", "text": "...", "why": "..."}],
 "faq_link": [{"question": "...", "faq_id": "...", "why": "..."}]}
"""


def brief(db: Session) -> str:
    """The whole prompt for `claude -p`: the instructions and the evidence."""
    return INSTRUCTIONS + "\n\nEVIDENCE (JSON):\n" + json.dumps(evidence(db), ensure_ascii=False, indent=1)


# --- Reading Claude's answer --------------------------------------------------------

def _json_in(text: str) -> dict:
    """The JSON object in Claude's answer, from `claude -p` plain or --output-format json."""
    t = (text or "").strip()
    try:
        outer = json.loads(t)
        if isinstance(outer, dict) and isinstance(outer.get("result"), str):
            t = outer["result"]
        elif isinstance(outer, dict):
            return outer
    except ValueError:
        pass
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        raise ValueError("Claude's answer has no JSON object in it")
    return json.loads(m.group(0))


def ingest(db: Session, answer: str) -> dict:
    """Checks Claude's proposals and adds the sound ones to the learning loop. Returns what was kept and dropped."""
    from src.services import agent_controls, eko_knowledge, learning_loop, nudge_messages
    from src.services import onboarding_bot as bot

    if not agent_controls.is_on(db, AGENT):
        return {"kept": 0, "dropped": ["The bot coach is switched off on the Agent quality page"]}
    data = _json_in(answer)
    run_id, at = uuid.uuid4().hex[:12], _now().isoformat()
    evidence_ = {"run_id": run_id, "agent": AGENT, "edit_ratio": None, "by": BY, "at": at}
    faq_ids = {f["id"]: f for f in eko_knowledge.FAQ}
    kept, dropped = [], []
    current = {s: learning_loop.nudge_delay(db, s).total_seconds() / 3600 for s in bot.NUDGE_STEPS}

    for p in data.get("nudge_timing") or []:
        step, hours, why = p.get("step"), p.get("hours"), (p.get("why") or "").strip()
        if step not in bot.NUDGE_STEPS or not isinstance(hours, (int, float)) or not MIN_HOURS <= hours <= MAX_HOURS:
            dropped.append(f"timing {step}={hours}: outside {MIN_HOURS}-{MAX_HOURS} h or not a bot question")
            continue
        hours = int(round(hours))
        if hours == round(current.get(step, 1)):
            continue
        kept.append({"id": _id("nudge_timing", step, hours), "kind": "nudge_timing", "agent": AGENT,
                     "step": step, "hours": hours,
                     "title": f"Reminder timing: {step.replace('_', ' ').lower()}",
                     "before": f"Reminder {round(current.get(step, 1))} h after the bot's question",
                     "after": f"Reminder {hours} h after the bot's question",
                     "lesson": f"Remind people {hours} h after the {step.replace('_', ' ').lower()} question. {why}".strip(),
                     "weight": 0.9, "evidence": evidence_})

    allowed = set(nudge_messages.PURPOSES) | {"bot_nudge"}
    for p in data.get("nudge_variant") or []:
        purpose, lang, text = p.get("purpose"), p.get("language"), (p.get("text") or "").strip()
        problems = eko_knowledge.vocabulary_problems(text)
        if purpose not in allowed or lang not in VARIANT_LANGS:
            dropped.append(f"version for {purpose}/{lang}: unknown purpose or language")
        elif not 15 <= len(text) <= MAX_VARIANT_CHARS or "{" in text:
            dropped.append(f"version for {purpose}/{lang}: too short, too long or has a placeholder")
        elif problems:
            dropped.append(f"version for {purpose}/{lang}: uses words Eko never uses ({', '.join(problems)})")
        else:
            base = learning_loop.base_text(purpose, lang)
            kept.append({"id": _id("nudge_variant", purpose, lang, text), "kind": "nudge_variant", "agent": AGENT,
                         "purpose": purpose, "language": lang, "text": text,
                         "title": f"New version of a reminder: {purpose.replace('_', ' ')} ({lang})",
                         "before": base, "after": text,
                         "lesson": f"Also send the {purpose.replace('_', ' ')} reminder ({lang}) this way: "
                                   f"{(p.get('why') or '').strip()}".strip(),
                         "weight": 0.6, "evidence": evidence_})

    for p in data.get("faq_link") or []:
        q, fid = (p.get("question") or "").strip()[:300], p.get("faq_id")
        if not q or fid not in faq_ids:
            dropped.append(f"answer link {fid}: unknown answer or empty question")
            continue
        kept.append({"id": _id("faq_link", fid, q.lower()), "kind": "faq_link", "agent": AGENT,
                     "faq_id": fid, "question": q,
                     "title": "A question the bot left for the team has an Eko answer",
                     "before": f"“{q}” → left for the team",
                     "after": f"“{q}” → Eko's answer: {faq_ids[fid]['question']}",
                     "lesson": f"Answer “{q}” with Eko's confirmed answer to “{faq_ids[fid]['question']}”. "
                               f"{(p.get('why') or '').strip()}".strip(),
                     "weight": 0.8, "evidence": evidence_})

    learning_loop.add_coach_proposals(db, kept, {"run_id": run_id, "at": at, "summary": (data.get("summary") or "")[:600],
                                                 "kept": len(kept), "dropped": len(dropped)})
    return {"kept": len(kept), "dropped": dropped, "summary": data.get("summary")}


# --- The two steps the host script runs inside the app (scripts/run_bot_coach.sh) ----
#   python -m src.services.bot_coach brief  > brief.txt
#   python -m src.services.bot_coach ingest < answer.json

def main(argv: List[str]) -> int:
    import sys
    from src.database import SessionLocal

    what = argv[1] if len(argv) > 1 else ""
    db = SessionLocal()
    try:
        if what == "brief":
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stdout.write(brief(db))
            return 0
        if what == "ingest":
            sys.stdin.reconfigure(encoding="utf-8")
            print(json.dumps(ingest(db, sys.stdin.read()), ensure_ascii=False))
            return 0
        print("Use: python -m src.services.bot_coach brief | ingest")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv))
