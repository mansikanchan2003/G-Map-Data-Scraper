"""
The admin's guardrails over AutoGMap's agents (the team's blueprint, phase 3,
2026-10-26): a one-click switch per agent that takes away its automatic
action, and switches for each piece of context the template agents are given.

Kept in app_settings under agent_controls, with who changed what and when.
Everything is on until the admin turns it off. Only an admin can change these
(routers/agents.py); every agent reads them each time it acts.
"""
import json
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from src.models.app_setting import AppSetting

KEY = "agent_controls"

# What each switch stops when it is off.
AGENTS: Dict[str, dict] = {
    "bot_reply_disposition": {"label": "Bot: dispositions read from replies",
                              "on": "Records a disposition when a reply says where the lead stands",
                              "off": "Replies are left as they are; the team records dispositions by hand"},
    "bot_faq": {"label": "Bot: FAQ answers",
                "on": "Answers questions from Eko's confirmed FAQ, trust concerns included",
                "off": "Every question goes to the team with a ticket; the bot only acknowledges it"},
    "template_writer": {"label": "Template Studio copywriter",
                        "on": "Writes template drafts for a state when asked",
                        "off": "New rounds are refused; drafts already written stay for review"},
    "business_agent": {"label": "Business-data template agent",
                       "on": "Writes template drafts from an uploaded sheet when asked",
                       "off": "New rounds are refused; drafts already written stay for review"},
    "inbox_ready_reply": {"label": "Inbox: ready replies",
                          "on": "Suggests a ready reply in the chat summary",
                          "off": "The summary suggests nothing; the team writes every reply"},
}
# The template agents' context, piece by piece (template_studio.prompt_context's sources).
CONTEXT: Dict[str, dict] = {
    "approved_example": {"label": "Approved examples", "about": "Meta-approved templates in the same language"},
    "performance": {"label": "Past performance", "about": "How earlier templates did: sends, reads, taps"},
    "rejected_draft": {"label": "Rejected drafts", "about": "Drafts a reviewer rejected, and why"},
    "past_mistake": {"label": "Past mistakes", "about": "Wording reviewers corrected before"},
    "growth_goal": {"label": "Growth goal", "about": "This month's lead goal and the funnel's weak step"},
    "accepted_lesson": {"label": "Accepted lessons", "about": "Patches the admin accepted from reviewers' corrections"},
}


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


def is_on(db: Session, agent: str) -> bool:
    return (_load(db).get("agents") or {}).get(agent, {}).get("on", True)


def context_on(db: Session, source: str) -> bool:
    return (_load(db).get("context") or {}).get(source, {}).get("on", True)


def state(db: Session) -> dict:
    data = _load(db)
    agents, context = data.get("agents") or {}, data.get("context") or {}
    return {
        "agents": [{"key": k, **meta, "enabled": agents.get(k, {}).get("on", True),
                    "changed_by": agents.get(k, {}).get("by"), "changed_at": agents.get(k, {}).get("at")}
                   for k, meta in AGENTS.items()],
        "context": [{"key": k, **meta, "enabled": context.get(k, {}).get("on", True),
                     "changed_by": context.get(k, {}).get("by"), "changed_at": context.get(k, {}).get("at")}
                    for k, meta in CONTEXT.items()],
        "history": (data.get("history") or [])[:20],
    }


def _set(db: Session, group: str, key: str, on: bool, by: str) -> dict:
    data = _load(db)
    data.setdefault(group, {})[key] = {"on": bool(on), "by": by, "at": _now()}
    label = (AGENTS if group == "agents" else CONTEXT)[key]["label"]
    data["history"] = [{"what": label, "on": bool(on), "by": by, "at": _now()}] + (data.get("history") or [])[:49]
    _save(db, data)
    return state(db)


def set_agent(db: Session, key: str, on: bool, by: str) -> dict:
    if key not in AGENTS:
        raise KeyError(key)
    return _set(db, "agents", key, on, by)


def set_context(db: Session, key: str, on: bool, by: str) -> dict:
    if key not in CONTEXT:
        raise KeyError(key)
    return _set(db, "context", key, on, by)


def refuse_if_off(db: Session, agent: str) -> Optional[str]:
    """Why an agent may not act now, or None."""
    if is_on(db, agent):
        return None
    return f"{AGENTS[agent]['label']} is turned off by the admin (Agent quality → Controls)."
