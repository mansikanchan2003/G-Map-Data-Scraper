"""
The learning loop (the team's blueprint, phase 4, 2026-10-26): what people
corrected becomes a proposed patch to the agents, which the admin accepts with
one click, after the golden set has run against it.

Proposals come from agent_runs a person corrected:
- copy_lesson: a sentence a reviewer rewrote in a template draft becomes a
  lesson for both template agents' prompts ("Write X rather than Y").
- rule_phrase: a reply the bot read as one disposition and the team recorded
  as another becomes a rule: that reply, read as the team's disposition.
- faq_review: an FAQ answer a person had to follow with their own reply is
  flagged for review. Eko's confirmed answers are never changed by a patch.

Accepted patches are kept in app_settings under learning_loop and are read by
the agents each time they act: lessons go into the copy prompts, rules are
checked before the bot's own. A rule is accepted only if the golden set's bot
suites still pass with it; any patch can be undone. Nothing here uses a
language model.
"""
import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterator, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.models.agent_runs import AgentRun
from src.models.app_setting import AppSetting

KEY = "learning_loop"
LOOKBACK_DAYS = 60
# A template correction smaller than this is a typo, not a lesson.
MIN_COPY_RATIO = 0.05
GATE_SUITES = ("reply_disposition", "trust", "bot_flow")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(db: Session) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == KEY).first()
    try:
        return json.loads(row.value) if row and row.value else {}
    except ValueError:
        return {}


def _save(db: Session, data: dict) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == KEY).first()
    if row is None:
        row = AppSetting(key=KEY)
        db.add(row)
    row.value = json.dumps(data)
    db.commit()


def _id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


# --- What the agents read --------------------------------------------------------

def lessons(db: Session) -> List[str]:
    """Accepted lessons for the template agents' prompts, newest first."""
    return [p["lesson"] for p in _load(db).get("accepted", []) if p["kind"] == "copy_lesson"]


def extra_rules(db: Session) -> List[Tuple[str, str]]:
    """Accepted rules for the bot: (disposition, the reply's words), checked before its own rules."""
    return [(p["key"], p["phrase"]) for p in _load(db).get("accepted", []) if p["kind"] == "rule_phrase"]


_extra_override: Optional[List[Tuple[str, str]]] = None


def rules_in_force(db: Session) -> List[Tuple[str, str]]:
    return _extra_override if _extra_override is not None else extra_rules(db)


def learned_reading(db: Session, said: str) -> Optional[str]:
    """The disposition an accepted rule gives this reply, or None."""
    t = _norm(said)
    for key, phrase in rules_in_force(db):
        if phrase and phrase in t:
            return key
    return None


@contextmanager
def trying(rules: List[Tuple[str, str]]) -> Iterator[None]:
    """Run with these rules in force (the gate and the playground), whatever is accepted."""
    global _extra_override
    saved = _extra_override
    _extra_override = rules
    try:
        yield
    finally:
        _extra_override = saved


# --- Proposals -------------------------------------------------------------------

def proposals(db: Session) -> List[dict]:
    """Patches the corrections suggest, biggest first; leaving out those already decided."""
    from src.services import dispositions as dz, template_studio

    data = _load(db)
    decided = {p["id"] for p in data.get("accepted", [])} | set(data.get("dismissed", {}))
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    out: Dict[str, dict] = {}
    runs = (db.query(AgentRun).filter(AgentRun.outcome == "edited", AgentRun.created_at >= since)
            .order_by(AgentRun.created_at.desc()).all())
    for r in runs:
        evidence = {"run_id": r.run_id, "agent": r.agent, "edit_ratio": r.edit_ratio,
                    "by": r.finalized_by, "at": r.finalized_at.isoformat() if r.finalized_at else None}
        if r.agent in ("template_writer", "business_agent") and (r.edit_ratio or 0) >= MIN_COPY_RATIO:
            for before, after in template_studio._corrections(r.output or "", r.final_output or "")[:3]:
                pid = _id("copy_lesson", _norm(before), _norm(after))
                if pid in decided or pid in out:
                    continue
                out[pid] = {"id": pid, "kind": "copy_lesson", "agent": r.agent, "before": before, "after": after,
                            "lesson": f"Write “{after}” rather than “{before}”: a reviewer corrected it.",
                            "title": "A reviewer rewrote a sentence", "weight": r.edit_ratio or 0,
                            "evidence": evidence}
        elif r.agent == "bot_reply_disposition" and r.final_output and r.prompt:
            key, phrase = r.final_output, _norm(r.prompt)[:120]
            if key not in dz.SUBS or not phrase:
                continue
            pid = _id("rule_phrase", key, phrase)
            if pid in decided or pid in out:
                continue
            was = "nothing (left to clarify)" if r.output == "clarify" else (dz.label(r.output) or r.output)
            out[pid] = {"id": pid, "kind": "rule_phrase", "agent": r.agent, "key": key, "phrase": phrase,
                        "before": f"“{r.prompt}” → {was}", "after": f"“{r.prompt}” → {dz.label(key)}",
                        "lesson": f"A reply like “{r.prompt}” means {dz.label(key)}.",
                        "title": "The team read a reply differently", "weight": 1.0, "evidence": evidence}
        elif r.agent == "bot_faq" and r.final_output:
            pid = _id("faq_review", _norm(r.prompt or ""))
            if pid in decided or pid in out:
                continue
            out[pid] = {"id": pid, "kind": "faq_review", "agent": r.agent, "before": r.output or "",
                        "after": r.final_output, "question": r.prompt,
                        "lesson": f"Review the FAQ answer to “{r.prompt}”: a person had to reply after the bot.",
                        "title": "A person followed up the bot's FAQ answer", "weight": r.edit_ratio or 0.5,
                        "evidence": evidence}
    return sorted(out.values(), key=lambda p: -p["weight"])


def _gate(rules: List[Tuple[str, str]]) -> dict:
    """
    The golden set's bot suites with these rules in force, run in a process of
    its own: the golden run swaps WhatsApp and the rest for stand-ins, which
    must never happen inside the live server.
    """
    import os
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # The child writes UTF-8 whatever the machine's code page (Windows would otherwise use cp1252).
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    try:
        done = subprocess.run([sys.executable, "-m", "src.evals.golden", "--suites", ",".join(GATE_SUITES),
                               "--rules", json.dumps(rules), "--json"], cwd=root, env=env, capture_output=True,
                              text=True, timeout=600, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"total": 1, "passed": 0, "failures": [{"id": "gate", "title": "The golden run took over 10 minutes",
                                                       "problems": ["Try again when the server is quieter."]}]}
    try:
        return json.loads((done.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"total": 1, "passed": 0, "failures": [{"id": "gate", "title": "The golden run did not finish",
                                                       "problems": [(done.stderr or "")[-300:]]}]}


class GateFailed(Exception):
    def __init__(self, report: dict):
        super().__init__("The golden set fails with this patch")
        self.report = report


def accept(db: Session, pid: str, by: str) -> dict:
    """Put a proposal into force. A rule must keep the golden set passing first."""
    p = next((x for x in proposals(db) if x["id"] == pid), None)
    if p is None:
        raise KeyError(pid)
    gate = None
    if p["kind"] == "rule_phrase":
        gate = _gate(extra_rules(db) + [(p["key"], p["phrase"])])
        if gate["passed"] < gate["total"]:
            raise GateFailed(gate)
    data = _load(db)
    entry = {**{k: v for k, v in p.items() if k != "weight"}, "accepted_by": by, "accepted_at": _now(),
             "gate": {"passed": gate["passed"], "total": gate["total"]} if gate else None}
    if p["kind"] == "faq_review":
        entry["lesson"] = f"Reviewed: the FAQ answer to “{p['question']}”."
    data["accepted"] = [entry] + data.get("accepted", [])
    data.setdefault("log", []).insert(0, {"what": "accepted", "id": pid, "lesson": entry["lesson"], "by": by, "at": _now()})
    _save(db, data)
    return entry


def dismiss(db: Session, pid: str, by: str) -> None:
    data = _load(db)
    data.setdefault("dismissed", {})[pid] = {"by": by, "at": _now()}
    data.setdefault("log", []).insert(0, {"what": "dismissed", "id": pid, "by": by, "at": _now()})
    _save(db, data)


def undo(db: Session, pid: str, by: str) -> None:
    data = _load(db)
    gone = [p for p in data.get("accepted", []) if p["id"] == pid]
    if not gone:
        raise KeyError(pid)
    data["accepted"] = [p for p in data.get("accepted", []) if p["id"] != pid]
    data.setdefault("log", []).insert(0, {"what": "undone", "id": pid, "lesson": gone[0].get("lesson"), "by": by, "at": _now()})
    _save(db, data)


def state(db: Session) -> dict:
    data = _load(db)
    return {"proposals": proposals(db), "accepted": data.get("accepted", []), "log": data.get("log", [])[:20]}


# --- Playground ------------------------------------------------------------------

def try_reply(db: Session, text: str) -> dict:
    """How the bot reads a reply today, and how it would with every pending rule accepted."""
    from src.services import dispositions as dz, reply_dispositions

    def reading(rules) -> dict:
        with trying(rules):
            learned = learned_reading(db, text)
        if learned:
            return {"key": learned, "label": dz.label(learned), "by": "an accepted rule", "confidence": 0.95}
        amb = reply_dispositions.ambiguous(text)
        if amb:
            return {"key": "clarify", "label": "Left for a person to clarify",
                    "by": " or ".join(dz.label(k) for k in amb), "confidence": None}
        hit = reply_dispositions.detect(text)
        if not hit:
            return {"key": None, "label": "Not read as a disposition", "by": "no rule matched", "confidence": None}
        return {"key": hit[0], "label": dz.label(hit[0]), "by": f"“{reply_dispositions.matched_phrase(text, hit[0])}”",
                "confidence": reply_dispositions.confidence(text, hit[0])}

    pending = [(p["key"], p["phrase"]) for p in proposals(db) if p["kind"] == "rule_phrase"]
    now = extra_rules(db)
    return {"text": text, "today": reading(now), "with_patches": reading(now + pending), "pending_rules": len(pending)}


_jobs: Dict[str, dict] = {}


def start_copy_trial(db: Session, state_name: str, instruction: str, without: List[str]) -> str:
    """Two drafts for one state: with today's prompt, and with the change. Runs in the background."""
    jid = uuid.uuid4().hex[:12]
    _jobs[jid] = {"status": "running", "state": state_name, "instruction": instruction, "without": without,
                  "started_at": _now()}
    return jid


def run_copy_trial(jid: str) -> None:
    """Background: write one variant each way and check both."""
    from src.database import SessionLocal
    from src.services import creative_brief, template_studio, variety
    from src.services.gemini_client import GeminiClient

    job = _jobs[jid]
    db = SessionLocal()
    try:
        language_code = creative_brief.language_for_state(job["state"])
        history = template_studio._review_history(db, job["state"])
        angles = template_studio.assign_angles(1, history["tried_keys"])
        plans = variety.plan(db, 1)
        section = variety.prompt_section(plans, variety.already_used(db, language_code))
        refs, perf, hist = template_studio.trimmed_context(
            db, template_studio.approved_examples(db, language_code), template_studio.template_performance(db), history)
        client = GeminiClient()

        def write(refs_, perf_, hist_, extra: str) -> dict:
            prompt = template_studio._copy_prompt(job["state"], language_code, angles, None, refs_, perf_, hist_, section)
            if extra:
                prompt += f"\n\nA CHANGE BEING TRIED (follow it): {extra}"
            v = template_studio._write_copy(client, prompt, angles, language_code)[0]
            v.pop("_first_errors", None)
            errors = v.pop("_errors", [])
            return {"body": v.get("body"), "angle": v.get("angle"), "problems": errors,
                    "prompt_tokens": -(-len(prompt) // 4)}

        a = write(refs, perf, hist, "")
        h2 = dict(hist)
        if "rejected_draft" in job["without"]:
            h2["rejected"] = []
        if "past_mistake" in job["without"]:
            h2["mistakes"] = []
        if "growth_goal" in job["without"]:
            h2["growth"] = None
        b = write([] if "approved_example" in job["without"] else refs,
                  [] if "performance" in job["without"] else perf, h2, job["instruction"])
        job.update(status="done", today=a, changed=b, finished_at=_now())
    except Exception as e:
        job.update(status="failed", error=str(e)[:300], finished_at=_now())
    finally:
        db.close()


def copy_trial(jid: str) -> Optional[dict]:
    return _jobs.get(jid)
