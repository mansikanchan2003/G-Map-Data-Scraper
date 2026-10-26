"""
Telemetry for AutoGMap's agents (the team's "agentic platform" blueprint,
2026-10-26): every run's full execution chain, [prompt + injected context
chunks + output + final human edit], in agent_runs, and the KPIs read from it.

The agents:
- template_writer: Template Studio's copywriter (a language model).
- business_agent: the business-data template agent (a language model).
- bot_faq: the bot answering a question from Eko's confirmed FAQ.
- bot_reply_disposition: the bot recording a disposition from a reply (fixed rules).
- inbox_ready_reply: the ready reply the Inbox summary offers the team.

What counts as the human's final version:
- a template draft: its body when a reviewer approves it (rejected: rejected);
- a ready reply: the text the team member actually sent;
- a bot FAQ answer: accepted unless a person had to reply in that chat
  within FAQ_WINDOW (then their reply is the correction);
- a reply disposition: accepted unless the team recorded another one
  within DISPOSITION_WINDOW (then theirs is the correction).

KPIs (metrics()): implicit acceptance rate (target > 75%), correction delta
(Levenshtein edit distance, target approaching 0), context window efficiency
(tokens per completed run, target falling), task completion rate (target
> 95%), and human-in-the-loop interventions (tickets, target falling).

Writes go in the caller's session inside a savepoint, so a telemetry failure
never breaks the agent's own work. Token counts are estimates (characters /
4) where the model reports none.
"""
import difflib
import logging
import math
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from src.models.agent_runs import AgentRun

logger = logging.getLogger("gmap_scraper.agent_telemetry")

AGENTS = {
    "template_writer": "Template Studio copywriter",
    "business_agent": "Business-data template agent",
    "bot_faq": "Bot: FAQ answers",
    "bot_reply_disposition": "Bot: dispositions read from replies",
    "inbox_ready_reply": "Inbox: ready replies",
}
TEMPLATE_AGENTS = ("template_writer", "business_agent")
# The context window of the model behind each agent, for the token health bar
# (the UI spec: green to 60%, yellow to 80%, red past it). The bot's agents use
# fixed rules and Eko's FAQ: no model, no window.
CONTEXT_WINDOW = {"template_writer": 128_000, "business_agent": 128_000}
# The three tiers of context (the UI spec, 2.1): global rules, the project's
# long-term memory, and this one session's input.
LAYER = {
    "facts": "global", "creator_pack": "global", "rules": "global", "trust_rule": "global", "rule": "global",
    "approved_example": "project", "performance": "project", "rejected_draft": "project",
    "past_mistake": "project", "growth_goal": "project", "faq": "project",
    "team_brief": "session", "audience": "session", "when": "session",
}


def layer_of(source: str) -> str:
    if source.startswith("learned:"):
        return "project"
    return LAYER.get(source, "session")
FAQ_WINDOW = timedelta(hours=2)
DISPOSITION_WINDOW = timedelta(hours=24)
TARGETS = {"acceptance": 0.75, "completion": 0.95}
CHUNK_CHARS = 600


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def tokens(text: Optional[str]) -> int:
    return math.ceil(len(text or "") / 4)


def levenshtein(a: str, b: str) -> int:
    """Edit distance; for very long texts, estimated from difflib's ratio to stay quick."""
    a, b = a or "", b or ""
    if a == b:
        return 0
    if len(a) * len(b) > 4_000_000:
        return round((1 - difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()) * max(len(a), len(b)))
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def chunk(source: str, text: Optional[str], ref: Optional[str] = None, score: Optional[float] = None) -> dict:
    """One piece of injected context, as kept: where it came from, a preview, and its size."""
    text = text or ""
    return {"source": source, "ref": ref, "text": text[:CHUNK_CHARS], "tokens": tokens(text), "score": score}


def _distance(output: Optional[str], final: Optional[str]) -> tuple:
    d = levenshtein(output or "", final or "")
    longest = max(len(output or ""), len(final or ""), 1)
    return d, round(d / longest, 4)


def log(db: Session, agent: str, subject_type: str, subject_id: str, output: Optional[str],
        prompt: Optional[str] = None, context: Optional[List[dict]] = None, model: Optional[str] = None,
        latency_ms: Optional[int] = None, outcome: str = "pending", error: Optional[str] = None,
        final_output: Optional[str] = None, finalized_by: Optional[str] = None,
        evaluation: Optional[dict] = None) -> Optional[str]:
    """Record one run. Returns its id, or None if it could not be recorded (the agent carries on)."""
    try:
        with db.begin_nested():
            run = AgentRun(run_id=uuid.uuid4().hex, agent=agent, subject_type=subject_type,
                           subject_id=str(subject_id)[:64], model=(model or None) and model[:120], prompt=prompt,
                           context=context or [], output=output, outcome=outcome, error=(error or None) and error[:500],
                           evaluation=evaluation,
                           prompt_tokens=tokens(prompt) if prompt else None,
                           context_tokens=sum(c.get("tokens") or 0 for c in (context or [])),
                           output_tokens=tokens(output) if output else None, latency_ms=latency_ms,
                           created_at=now())
            if final_output is not None or outcome in ("accepted", "edited", "rejected"):
                _settle(run, final_output, finalized_by, outcome if outcome != "pending" else None)
            db.add(run)
        return run.run_id
    except Exception:
        logger.exception(f"agent_telemetry event=LOG_FAILED agent={agent}")
        return None


def _settle(run: AgentRun, final: Optional[str], by: Optional[str], outcome: Optional[str] = None) -> None:
    run.final_output = final
    run.finalized_by = by
    run.finalized_at = now()
    if outcome == "rejected":
        run.outcome = "rejected"
        return
    run.edit_distance, run.edit_ratio = _distance(run.output, final if final is not None else run.output)
    run.outcome = outcome or ("accepted" if run.edit_distance == 0 else "edited")


def finalize(db: Session, agents: Iterable[str], subject_id: str, final: Optional[str], by: Optional[str],
             outcome: Optional[str] = None) -> int:
    """A person's final version for the pending runs of these agents on this subject. Returns how many."""
    try:
        with db.begin_nested():
            runs = db.query(AgentRun).filter(AgentRun.agent.in_(list(agents)), AgentRun.subject_id == str(subject_id),
                                             AgentRun.outcome == "pending").all()
            for r in runs:
                _settle(r, final, by, outcome)
        return len(runs)
    except Exception:
        logger.exception(f"agent_telemetry event=FINALIZE_FAILED subject={subject_id}")
        return 0


def disposition_overridden(db: Session, phone: str, key: str, by: str) -> None:
    """The team recorded a disposition: the bot's reading of a reply in the day before is judged by it."""
    since = now() - DISPOSITION_WINDOW
    try:
        with db.begin_nested():
            for r in db.query(AgentRun).filter(AgentRun.agent == "bot_reply_disposition", AgentRun.subject_id == phone,
                                               AgentRun.outcome == "pending").all():
                if _aware(r.created_at) >= since:
                    _settle(r, key, by, "accepted" if key == r.output else "edited")
    except Exception:
        logger.exception("agent_telemetry event=OVERRIDE_FAILED")


def settle(db: Session, at: Optional[datetime] = None) -> int:
    """
    Judge the bot's runs once their window has passed: an FAQ answer a person
    had to follow with their own reply is corrected by that reply; anything
    else left alone is accepted. Returns how many were settled.
    """
    from src.models.inbox import WhatsAppMessage

    at = at or now()
    n = 0
    for r in db.query(AgentRun).filter(AgentRun.outcome == "pending",
                                       AgentRun.agent.in_(("bot_faq", "bot_reply_disposition"))).all():
        made = _aware(r.created_at)
        if r.agent == "bot_faq" and at - made >= FAQ_WINDOW:
            reply = (db.query(WhatsAppMessage)
                     .filter(WhatsAppMessage.phone == r.subject_id, WhatsAppMessage.direction == "OUT",
                             WhatsAppMessage.sent_by.like("%@%"), WhatsAppMessage.created_at >= made,
                             WhatsAppMessage.created_at <= made + FAQ_WINDOW)
                     .order_by(WhatsAppMessage.created_at).first())
            if reply:
                _settle(r, reply.body or "", reply.sent_by, "edited")
            else:
                _settle(r, None, "implicit", "accepted")
            n += 1
        elif r.agent == "bot_reply_disposition" and at - made >= DISPOSITION_WINDOW:
            _settle(r, None, "implicit", "accepted")
            n += 1
    db.flush()
    return n


def _rate(num: int, den: int) -> Optional[float]:
    return round(num / den, 4) if den else None


def _summary(runs: List[AgentRun]) -> dict:
    done = [r for r in runs if r.outcome != "failed"]
    decided = [r for r in runs if r.outcome in ("accepted", "edited", "rejected")]
    judged = [r for r in runs if r.outcome in ("accepted", "edited") and r.edit_distance is not None]
    tok = [(r.prompt_tokens or 0) + (r.context_tokens or 0) + (r.output_tokens or 0) for r in done]
    return {
        "runs": len(runs),
        "failed": len(runs) - len(done),
        "pending": sum(r.outcome == "pending" for r in runs),
        "accepted": sum(r.outcome == "accepted" for r in runs),
        "edited": sum(r.outcome == "edited" for r in runs),
        "rejected": sum(r.outcome == "rejected" for r in runs),
        "completion_rate": _rate(len(done), len(runs)),
        "acceptance_rate": _rate(sum(r.outcome == "accepted" for r in decided), len(decided)),
        "avg_edit_distance": round(sum(r.edit_distance for r in judged) / len(judged), 1) if judged else None,
        "avg_edit_ratio": round(sum(r.edit_ratio or 0 for r in judged) / len(judged), 4) if judged else None,
        "tokens_per_run": round(sum(tok) / len(tok)) if tok else None,
        "context_tokens_per_run": round(sum(r.context_tokens or 0 for r in done) / len(done)) if done else None,
    }


def _week(dt: datetime) -> str:
    d = _aware(dt).date()
    return (d - timedelta(days=d.weekday())).isoformat()


def metrics(db: Session, days: int = 30) -> dict:
    """The blueprint's KPIs, per agent and week by week, with the human-in-the-loop count."""
    from src.models.inbox import AttentionTicket

    since = now() - timedelta(days=days)
    runs = db.query(AgentRun).filter(AgentRun.created_at >= since).all()
    by_agent: Dict[str, List[AgentRun]] = defaultdict(list)
    for r in runs:
        by_agent[r.agent].append(r)
    weeks: Dict[str, List[AgentRun]] = defaultdict(list)
    for r in runs:
        weeks[_week(r.created_at)].append(r)
    tickets = db.query(AttentionTicket).filter(AttentionTicket.raised_at >= since).all()
    hitl_weeks: Dict[str, int] = defaultdict(int)
    for t in tickets:
        hitl_weeks[_week(t.raised_at)] += 1
    all_weeks = sorted(set(weeks) | set(hitl_weeks))
    edited = sorted((r for r in runs if r.outcome == "edited" and r.edit_ratio), key=lambda r: -(r.edit_ratio or 0))
    return {
        "days": days,
        "targets": {"acceptance_rate": TARGETS["acceptance"], "completion_rate": TARGETS["completion"],
                    "avg_edit_ratio": 0.0},
        # Drift & repair: where people changed the most, to learn from first.
        "biggest_corrections": [as_dict(r) for r in edited[:5]],
        "overall": _summary(runs),
        "agents": [{"key": k, "label": label, **_summary(by_agent.get(k, []))} for k, label in AGENTS.items()],
        "hitl_interventions": len(tickets),
        "weeks": [{"week": w, **{k: v for k, v in _summary(weeks.get(w, [])).items()
                                 if k in ("runs", "acceptance_rate", "avg_edit_ratio", "tokens_per_run",
                                          "completion_rate")},
                   "hitl": hitl_weeks.get(w, 0)} for w in all_weeks],
    }


def as_dict(r: AgentRun, full: bool = False) -> dict:
    out = {"id": r.run_id, "agent": r.agent, "agent_label": AGENTS.get(r.agent, r.agent),
           "subject_type": r.subject_type, "subject_id": r.subject_id, "model": r.model, "outcome": r.outcome,
           "output": r.output, "final_output": r.final_output, "edit_distance": r.edit_distance,
           "edit_ratio": r.edit_ratio, "prompt_tokens": r.prompt_tokens, "context_tokens": r.context_tokens,
           "output_tokens": r.output_tokens, "latency_ms": r.latency_ms, "error": r.error,
           "finalized_by": r.finalized_by,
           "context": [{**c, "layer": layer_of(c.get("source") or "")} for c in (r.context or [])],
           "evaluation": r.evaluation, "context_window": CONTEXT_WINDOW.get(r.agent),
           "created_at": _aware(r.created_at).isoformat() if r.created_at else None,
           "finalized_at": _aware(r.finalized_at).isoformat() if r.finalized_at else None}
    if full:
        out["prompt"] = r.prompt
    return out


def recent(db: Session, agent: Optional[str] = None, outcome: Optional[str] = None, limit: int = 50) -> List[dict]:
    q = db.query(AgentRun)
    if agent:
        q = q.filter(AgentRun.agent == agent)
    if outcome:
        q = q.filter(AgentRun.outcome == outcome)
    return [as_dict(r) for r in q.order_by(AgentRun.created_at.desc()).limit(limit).all()]
