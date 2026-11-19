"""
Claude answers the questions the bot cannot (the user, 19 Nov 2026), and the bot learns them.

The bot answers from Eko's confirmed FAQ first; only a question it has no answer for reaches
Claude, so Claude is asked rarely. That question is already a ticket for the team. A host
script on the server (scripts/run_claude_answers.sh, every minute) takes the waiting ones out
(`python -m src.services.claude_answers pending`), asks Mansi's own Claude CLI on the server
(`claude -p`, no tools, one turn, the way the bot coach runs), and hands each answer back
(`python -m src.services.claude_answers answer`). No login or key of hers is inside the app.

What goes out: the question with names, numbers and emails taken out, the person's language
and which programme they are in (SBI or ESAF), and Eko's confirmed facts. Nothing else.

An answer is sent only if it is sound: Claude says it can answer, and it keeps Eko's word
rules (eko_knowledge.vocabulary_problems: never "zero investment", no commission figures...).
Then the ticket is solved "by Claude CLI", and the answer joins the learning loop as an
accepted entry: the next time someone asks the same question, in other words too, the bot
sends it itself (same matching as "Teach the bot"), with no call to Claude. Undoing the entry
in the learning loop stops that. Otherwise the ticket stays with the team, as before.

AGENT switch "claude_answers" on the Agent quality page turns it off.
"""
import json
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

AGENT = "claude_answers"
BY = "claude_cli"
LABEL = "Claude CLI"
KIND = "claude_answer"
# A question waits this long for Claude; after that it is the team's alone.
WAIT = timedelta(hours=6)
# WhatsApp lets us write freely for 24 hours after their message.
WINDOW = timedelta(hours=23)
MAX_ANSWER_CHARS = 900
LANGS = ("en", "hi", "hinglish", "gu", "mr", "pa", "bn", "ta", "te", "kn", "ml", "or")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Optional[str]) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(v) if v else None
    except ValueError:
        return None
    return d.replace(tzinfo=timezone.utc) if d and d.tzinfo is None else d


# --- Learned answers: the bot gives them itself ---------------------------------------

def learned(db: Session) -> List[dict]:
    from src.services import learning_loop
    return [p for p in learning_loop._load(db).get("accepted", []) if p.get("kind") == KIND]


def _share(a: str, b: str) -> float:
    """How much two questions say the same thing, by the words that matter (eko_knowledge's matching)."""
    from src.services import eko_knowledge as ek
    aw, bw = ek._words(a), ek._words(b)
    said = ek._content(aw, [ek._sound(w) for w in aw])
    known = ek._content(bw, [ek._sound(w) for w in bw])
    if len(said) < 2 or len(known) < 2:
        return 0.0
    hits = [p for p, _ in known if any(ek._same(p, w, s) for w, s in said)]
    if len(hits) < 2 or all(h in ek._QUESTION_WORDS for h in hits):
        return 0.0
    return len(hits) / max(len(known), len(said))


def match(db: Session, said: str) -> Optional[dict]:
    """The learned answer whose question this one nearly repeats; None when none is clear."""
    scored = []
    for entry in learned(db):
        best = max([_share(said, q) for q in [entry.get("question", "")] + entry.get("also", [])] or [0.0])
        if best >= 0.6:
            scored.append((best, entry))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    if len(scored) > 1 and scored[1][0] > scored[0][0] - 0.1 and scored[1][1]["id"] != scored[0][1]["id"]:
        return None   # two answers about as close: better a person than a guess
    return scored[0][1]


def answer_in(entry: dict, lang: str, said: str = "") -> str:
    """
    The learned answer in the person's own language; "" when Claude has not given it in that
    language yet (19 Nov 2026): then Claude is asked again, never the wrong language sent.
    """
    from src.services import eko_knowledge as ek
    answers = entry.get("answers") or {}
    if lang == "hi" and said and ek._LATIN.search(said) and not re.search(r"[ऀ-ॿ]", said):
        return answers.get("hinglish") or ""
    return answers.get(lang) or ""


def remember_wording(db: Session, entry_id: str, said: str) -> None:
    """Another way of asking it, kept with the answer (at most 20)."""
    from src.services import learning_loop
    data = learning_loop._load(db)
    for p in data.get("accepted", []):
        if p.get("id") == entry_id:
            also = p.setdefault("also", [])
            q = " ".join((said or "").split())[:300]
            if q and q not in also and q != p.get("question") and len(also) < 20:
                also.append(q)
                learning_loop._save(db, data)
            return


# --- Asking Claude ---------------------------------------------------------------------

def on(db: Session) -> bool:
    from src.services import agent_controls
    return agent_controls.is_on(db, AGENT)


def ask(db: Session, conv, said: str, lang: str, learned_id: Optional[str] = None) -> None:
    """
    A question the bot could not answer, already a ticket: queued for Claude. `learned_id` is
    a learned answer that has no version in this language yet: Claude's reply is added to it.
    """
    from src.services import bot_coach, handover
    if not on(db) or not (said or "").strip():
        return
    names = [n for n in (conv.profile_name or "").split() if len(n) > 2]
    conv.bot_data = {**(conv.bot_data or {}), "claude_ask": {
        "id": uuid.uuid4().hex[:16], "question": bot_coach.redact(said, names)[:600], "lang": lang,
        "programme": handover.programme(conv), "at": _now().isoformat(), "state": "waiting",
        "learned_id": learned_id}}
    flag_modified(conv, "bot_data")


RULES = """RULES (Eko's, never break them):
- SBI CSP (Kiosk Operator): an investment of ₹3–5 lakh depending on location; the money stays the operator's own, in their e-wallet, used to serve customers. Eko delivers and sets up the devices, trains them, and an SBI branch is attached.
- ESAF Small Finance Bank's banking agent is for people who cannot invest for SBI: ₹1,999 registration (mandatory); a Micro ATM costs ₹1,300 + GST only if they take one. Say "koi bada investment nahi" (no big investment), never "zero investment". Only for 12th pass or above.
- Never give commission figures or monthly earnings numbers. Never promise approval, a branch or a date.
- Never ask for Aadhaar, PAN or bank details in the chat: documents go through the upload link the bot sends.
- Do not invent facts. If the facts below do not answer it, or it needs a person (a complaint, their own case, money already paid), set can_answer to false."""


def prompt(item: dict) -> str:
    from src.services import eko_knowledge as ek
    faq = "\n".join(f"- {f['question']} → {f['answer'].get('en') or f['answer'].get('hinglish')}" for f in ek.FAQ)
    lang = item.get("lang") or "hi"
    return f"""You answer one WhatsApp question for Eko India Financial Services. The person may become an Eko Kiosk Operator and open an SBI Customer Service Point (CSP), or, if they cannot invest, an ESAF Small Finance Bank banking agent. They are in the {"ESAF" if item.get("programme") == "esaf" else "SBI"} flow. Eko's WhatsApp bot could not answer this question, so you answer it.

{RULES}

EKO'S CONFIRMED FACTS (use only these):
{faq}

THE QUESTION (language code: {lang}; "hinglish" means Hindi in Latin letters):
{item.get("question")}

Reply with ONLY a JSON object, no other text:
{{"can_answer": true or false, "answer": "the reply in the person's own language and script, warm and polite, plain WhatsApp text, under 80 words", "answer_en": "the same in English", "answer_hi": "the same in Hindi (Devanagari)", "answer_hinglish": "the same in Hinglish", "why": "if can_answer is false, why"}}"""


def pending(db: Session) -> List[dict]:
    """Everything waiting for Claude, each with its prompt: questions, then interest ratings."""
    return pending_questions(db) + interest_pending(db)


def pending_questions(db: Session) -> List[dict]:
    """The questions waiting for Claude, each with its prompt."""
    from src.models.inbox import WhatsAppConversation
    from src.services import tickets
    if not on(db):
        return []
    out = []
    now = _now()
    for conv in db.query(WhatsAppConversation).filter(WhatsAppConversation.needs_attention.is_(True)).all():
        a = (conv.bot_data or {}).get("claude_ask")
        if not a or a.get("state") != "waiting":
            continue
        at, last_in = _iso(a.get("at")), conv.last_inbound_at
        last_in = last_in.replace(tzinfo=timezone.utc) if last_in and last_in.tzinfo is None else last_in
        if not at or now - at > WAIT or not last_in or now - last_in > WINDOW or not tickets.open_ticket(db, conv.phone):
            continue
        out.append({"id": a["id"], "prompt": prompt(a)})
    return out


def _parse(text: str) -> dict:
    from src.services import bot_coach
    try:
        outer = json.loads(text)
        if isinstance(outer, dict) and isinstance(outer.get("result"), str):
            text = outer["result"]
        elif isinstance(outer, dict) and "can_answer" in outer:
            return outer
    except ValueError:
        pass
    return bot_coach._json_in(text)


def ingest(db: Session, ask_id: str, claude_output: str) -> dict:
    """Claude's answer to one waiting question: sent and learned if sound, else left for the team."""
    if ask_id.startswith(INTEREST_PREFIX):
        return interest_ingest(db, ask_id, claude_output)
    from src.models.inbox import WhatsAppConversation
    from src.services import eko_knowledge as ek, learning_loop, onboarding_bot as bot, tickets

    conv = next((c for c in db.query(WhatsAppConversation).filter(WhatsAppConversation.needs_attention.is_(True)).all()
                 if ((c.bot_data or {}).get("claude_ask") or {}).get("id") == ask_id), None)
    if conv is None:
        return {"id": ask_id, "done": False, "why": "no longer waiting (a person answered, or it was solved)"}
    a = dict(conv.bot_data["claude_ask"])

    def leave(why: str) -> dict:
        a.update(state="left", why=why[:300])
        conv.bot_data = {**conv.bot_data, "claude_ask": a}
        flag_modified(conv, "bot_data")
        db.commit()
        return {"id": ask_id, "done": False, "why": why}

    try:
        got = _parse(claude_output)
    except Exception:
        return leave("Claude's reply was not readable")
    answer = " ".join(str(got.get("answer") or "").split(" ")).strip()
    if not got.get("can_answer") or not answer:
        return leave(f"Claude could not answer: {got.get('why') or 'no answer'}")
    if len(answer) > MAX_ANSWER_CHARS:
        return leave("Claude's answer was too long")
    answers = {"en": got.get("answer_en"), "hi": got.get("answer_hi"), "hinglish": got.get("answer_hinglish")}
    answers = {k: str(v).strip() for k, v in answers.items() if v and str(v).strip()}
    lang = a.get("lang") if a.get("lang") in LANGS else "hi"
    answers[lang] = answer          # what they are sent, in their own language, always kept
    problems = [p for text in answers.values() for p in ek.vocabulary_problems(text)]
    if problems:
        return leave("Claude's answer broke Eko's word rules: " + "; ".join(problems[:3]))
    if not tickets.open_ticket(db, conv.phone):
        return leave("the ticket was already solved")

    bot._say(db, conv, answer)
    ticket = tickets.resolve(db, conv.phone, BY)
    if ticket is not None:
        ticket.bot_answer = answer
    conv.needs_attention = False
    conv.attention_resolved_by, conv.attention_resolved_at = LABEL, _now()
    a.update(state="answered", answered_at=_now().isoformat())
    conv.bot_data = {**conv.bot_data, "claude_ask": a}
    flag_modified(conv, "bot_data")
    db.commit()

    data = learning_loop._load(db)
    known = next((p for p in data.get("accepted", []) if p.get("id") == a.get("learned_id")), None)
    if known is not None:
        # The same question in another language: its answer joins the one already learned.
        known.setdefault("answers", {}).update({k: v for k, v in answers.items() if k not in known["answers"]})
        learning_loop._save(db, data)
        return {"id": ask_id, "done": True, "ticket": ticket.ticket_id if ticket is not None else None}
    eid = learning_loop._id(KIND, learning_loop._norm(a["question"]))
    if not any(p.get("id") == eid for p in data.get("accepted", [])):
        entry = {"id": eid, "kind": KIND, "agent": AGENT, "question": a["question"], "lang": a.get("lang"),
                 "answers": answers, "programme": a.get("programme"), "title": "Claude CLI answered a new question",
                 "lesson": f"Asked “{a['question'][:160]}”, the bot now answers: “{answer[:200]}”",
                 "before": a["question"], "after": answer, "accepted_by": LABEL, "accepted_at": _now().isoformat(),
                 "ticket_id": ticket.ticket_id if ticket is not None else None}
        data["accepted"] = [entry] + data.get("accepted", [])
        data.setdefault("log", []).insert(0, {"what": "learned", "id": eid, "lesson": entry["lesson"], "by": LABEL,
                                              "at": _now().isoformat()})
        learning_loop._save(db, data)
    return {"id": ask_id, "done": True, "ticket": ticket.ticket_id if ticket is not None else None}


# --- How interested someone is, after our nudges went unanswered (19 Nov 2026) --------------
#
# After NUDGES_BEFORE_RATING of the bot's messages since their last reply, Claude reads the
# chat (names and numbers taken out) and rates their interest: high, medium, low or not
# interested, with one line why. Shown on the Applications tab and in the chat. Rated again
# when they write or after another nudge. A label only: nothing is sent, no disposition is set.

INTEREST_PREFIX = "int:"
NUDGES_BEFORE_RATING = 3
INTEREST_LEVELS = ("high", "medium", "low", "not_interested")
INTEREST_PER_RUN = 15
# The bot's own reply right after theirs is not a nudge.
REPLY_GAP = timedelta(minutes=10)


def _aware(d):
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def nudges_since_reply(messages: list) -> int:
    """Our messages after their last one, leaving out the bot's immediate reply."""
    last_in = max((_aware(m.created_at) for m in messages if m.direction == "IN"), default=None)
    outs = [_aware(m.created_at) for m in messages if m.direction == "OUT" and m.created_at is not None]
    if last_in is None:
        return 0
    return sum(1 for at in outs if at > last_in + REPLY_GAP)


def _interest_brief(conv, messages: list) -> str:
    from src.services import bot_coach, handover
    from src.services import onboarding_bot as bot
    names = [n for n in (conv.profile_name or "").split() if len(n) > 2]
    lines = []
    for m in messages[-16:]:
        text = (m.body or "").strip() or (m.payload or {}).get("transcript") or f"[{m.kind}]"
        who = "THEM" if m.direction == "IN" else "US"
        lines.append(f"{who}: {bot_coach.redact(text, names)[:240]}")
    step = bot.STEP_LABELS.get(conv.bot_step, conv.bot_step or "not started")
    return f"""You judge how interested a person is in becoming an Eko Kiosk Operator ({"ESAF banking agent" if handover.programme(conv) == "esaf" else "SBI Customer Service Point"}), from their WhatsApp chat with Eko. We have sent them {nudges_since_reply(messages)} messages since their last reply. Where they stopped in our questions: {step}.

THE CHAT, oldest first (THEM = the person, US = Eko and its bot; names and numbers removed):
{chr(10).join(lines)}

Judge mostly from THEIR last messages and how they stopped. Reply with ONLY a JSON object:
{{"level": "high" | "medium" | "low" | "not_interested", "reason": "one plain English line, under 20 words, why"}}"""


def interest_pending(db: Session) -> List[dict]:
    from src.models.inbox import WhatsAppConversation, WhatsAppMessage
    from src.services import applications
    if not on(db):
        return []
    out = []
    convs = [c for c in db.query(WhatsAppConversation).filter(WhatsAppConversation.bot_step.isnot(None)).all()
             if applications.is_application(c) and not c.documents_submitted_at]
    for conv in convs:
        messages = (db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == conv.phone)
                    .order_by(WhatsAppMessage.created_at).all())
        if nudges_since_reply(messages) < NUDGES_BEFORE_RATING or not messages:
            continue
        latest = _aware(messages[-1].created_at)
        held = (conv.bot_data or {}).get("interest") or {}
        if held.get("basis_at") and _iso(held["basis_at"]) and _iso(held["basis_at"]) >= latest:
            continue          # rated on these very messages
        out.append({"id": f"{INTEREST_PREFIX}{conv.phone.lstrip('+')}:{int(latest.timestamp())}",
                    "prompt": _interest_brief(conv, messages)})
        if len(out) >= INTEREST_PER_RUN:
            break
    return out


def interest_ingest(db: Session, ask_id: str, claude_output: str) -> dict:
    from src.models.inbox import WhatsAppConversation
    try:
        _, digits, stamp = ask_id.split(":")
    except ValueError:
        return {"id": ask_id, "done": False, "why": "not an interest id"}
    conv = db.get(WhatsAppConversation, "+" + digits) or db.get(WhatsAppConversation, digits)
    if conv is None:
        return {"id": ask_id, "done": False, "why": "no such chat"}
    try:
        got = _parse(claude_output)
    except Exception:
        return {"id": ask_id, "done": False, "why": "Claude's reply was not readable"}
    level = str(got.get("level") or "").strip().lower().replace(" ", "_")
    if level not in INTEREST_LEVELS:
        return {"id": ask_id, "done": False, "why": f"unknown level {level!r}"}
    reason = " ".join(str(got.get("reason") or "").split())[:200]
    conv.bot_data = {**(conv.bot_data or {}), "interest": {
        "level": level, "reason": reason, "at": _now().isoformat(),
        "basis_at": datetime.fromtimestamp(int(stamp), timezone.utc).isoformat(), "by": LABEL}}
    flag_modified(conv, "bot_data")
    db.commit()
    return {"id": ask_id, "done": True, "level": level}


def interest_of(conv) -> Optional[dict]:
    held = (conv.bot_data or {}).get("interest") if conv is not None else None
    if not held or held.get("level") not in INTEREST_LEVELS:
        return None
    return {k: held.get(k) for k in ("level", "reason", "at")}


def main(argv: List[str]) -> int:
    from src.database import SessionLocal
    db = SessionLocal()
    try:
        if argv[:1] == ["pending"]:
            sys.stdout.write(json.dumps(pending(db), ensure_ascii=False))
        elif argv[:1] == ["answer"] and len(argv) == 2:
            sys.stdout.write(json.dumps(ingest(db, argv[1], sys.stdin.read()), ensure_ascii=False) + "\n")
        else:
            sys.stderr.write("usage: python -m src.services.claude_answers pending | answer <id> < claude.json\n")
            return 2
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
