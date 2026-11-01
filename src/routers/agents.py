"""
The Agent quality page: how AutoGMap's agents are doing (agent_telemetry.py),
and each run's full chain, with the context it used, for the "why".
"""
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.user import User
from src.routers.auth import current_admin, current_user
from src.services import agent_controls
from src.models.agent_runs import AgentRun
from src.services import agent_telemetry

router = APIRouter(prefix="/api/v1/agents", tags=["Agent quality"])


@router.get("/quality")
def quality(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    """Implicit acceptance, correction delta, tokens per run, completion and human interventions."""
    return agent_telemetry.metrics(db, days)


@router.get("/golden")
def golden_report(db: Session = Depends(get_db)):
    """The golden set's last run before a deploy (python -m src.evals.golden --save), and the ones before."""
    from src.evals import golden
    return golden.latest(db) or {"last": None, "history": []}


@router.get("/runs")
def runs(agent: Optional[str] = None, outcome: Optional[str] = None, subject: Optional[str] = None,
         limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    """The latest runs, newest first: output, final version, edit distance and the context used."""
    return agent_telemetry.recent(db, agent, outcome, limit, subject)


@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    """Each source the agents use, with when it was last refreshed."""
    return agent_telemetry.sources(db)


class SwitchRequest(BaseModel):
    enabled: bool


class TextRequest(BaseModel):
    text: str


class CopyTrialRequest(BaseModel):
    state: str
    instruction: str = ""
    without: list = []


@router.get("/learning")
def learning(db: Session = Depends(get_db)):
    """The learning loop: patches proposed from corrections, those accepted, and what was done."""
    from src.services import learning_loop
    return learning_loop.state(db)


@router.post("/learning/{pid}/accept")
def accept_patch(pid: str, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    """Put a patch into force (admin only). A rule must keep the golden set passing first."""
    from src.services import learning_loop
    try:
        return learning_loop.accept(db, pid, admin.email)
    except KeyError:
        raise HTTPException(status_code=404, detail="No such proposal")
    except learning_loop.GateFailed as e:
        raise HTTPException(status_code=409, detail={"message": "The golden set fails with this patch, so it was not accepted.",
                                                     "gate": e.report})


@router.post("/learning/{pid}/dismiss")
def dismiss_patch(pid: str, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    from src.services import learning_loop
    learning_loop.dismiss(db, pid, admin.email)
    return learning_loop.state(db)


@router.post("/learning/{pid}/undo")
def undo_patch(pid: str, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    from src.services import learning_loop
    try:
        learning_loop.undo(db, pid, admin.email)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not an accepted patch")
    return learning_loop.state(db)


@router.post("/playground/reply")
def playground_reply(req: TextRequest, db: Session = Depends(get_db)):
    """How the bot reads a reply today, and with every pending rule accepted."""
    from src.services import learning_loop
    return learning_loop.try_reply(db, req.text.strip()[:500])


@router.post("/playground/copy")
def playground_copy(req: CopyTrialRequest, background: BackgroundTasks, db: Session = Depends(get_db),
                    admin: User = Depends(current_admin)):
    """Two drafts side by side: today's prompt, and with the change (admin only; uses the free model)."""
    from src.services import creative_brief, learning_loop
    if not creative_brief.language_for_state(req.state):
        raise HTTPException(status_code=400, detail=f"No language is set for {req.state}.")
    jid = learning_loop.start_copy_trial(db, req.state, req.instruction.strip()[:600], [str(w) for w in req.without])
    background.add_task(learning_loop.run_copy_trial, jid)
    return {"id": jid}


@router.get("/playground/copy/{jid}")
def playground_copy_result(jid: str):
    from src.services import learning_loop
    job = learning_loop.copy_trial(jid)
    if job is None:
        raise HTTPException(status_code=404, detail="No such trial")
    return job


@router.get("/controls")
def controls(db: Session = Depends(get_db)):
    """The admin's guardrails: each agent's switch and each context source's."""
    return agent_controls.state(db)


@router.put("/controls/agents/{key}")
def switch_agent(key: str, req: SwitchRequest, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    """Turn an agent's automatic action on or off (admin only)."""
    try:
        return agent_controls.set_agent(db, key, req.enabled, admin.email)
    except KeyError:
        raise HTTPException(status_code=404, detail="No such agent")


@router.put("/controls/context/{key}")
def switch_context(key: str, req: SwitchRequest, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    """Give the template agents a context source, or take it away (admin only)."""
    try:
        return agent_controls.set_context(db, key, req.enabled, admin.email)
    except KeyError:
        raise HTTPException(status_code=404, detail="No such context source")


# --- Personal data: how long it is kept (services/retention) -----------------------

class RetentionPolicy(BaseModel):
    enabled: bool = False
    documents_days: Optional[int] = None
    chat_days: Optional[int] = None
    # What the periods rest on, e.g. "Confirmed by compliance on 5 Nov 2026".
    basis: Optional[str] = None


class CleanItem(BaseModel):
    phone: str
    scope: str


class CleanRequest(BaseModel):
    # Exactly what the admin was shown: only these, if still due, are cleaned up.
    items: List[CleanItem]


@router.get("/retention")
def retention_state(db: Session = Depends(get_db)):
    """The retention policy, what is due under it now, and the do-not-message list's size."""
    from src.models.opt_out import OptOut
    from src.services import opt_out, retention
    by = {}
    for (source,) in db.query(OptOut.source).all():
        by[source] = by.get(source, 0) + 1
    return {"policy": retention.policy(db), "due": retention.due(db),
            "opt_outs": {"total": sum(by.values()), "by_source": by, "sources": opt_out.SOURCES}}


@router.put("/retention")
def set_retention(req: RetentionPolicy, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    """Set how long documents and chats are kept (admin only). Off until both periods and their basis are set."""
    from src.services import retention
    for days in (req.documents_days, req.chat_days):
        if days is not None and not 30 <= days <= 3650:
            raise HTTPException(status_code=400, detail="A period must be between 30 days and 10 years.")
    try:
        out = retention.set_policy(db, admin.email, req.enabled, req.documents_days, req.chat_days, req.basis)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return out


@router.post("/retention/clean")
def clean_up(req: CleanRequest, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    """Clean up what the admin confirmed from the due list (admin only)."""
    from src.services import retention
    out = retention.clean(db, [i.model_dump() for i in req.items], admin.email)
    db.commit()
    return out


# --- The audit log (services/audit) ---------------------------------------------------

@router.get("/audit")
def audit_log(limit: int = Query(200, ge=1, le=1000), actor: Optional[str] = None, action: Optional[str] = None,
              db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Who changed what, newest first (admin and manager only). Read-only: nothing here edits or deletes a row."""
    if user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Only the admin and managers can read the audit log")
    from src.services import audit, campaign_approval
    rows = audit.recent(db, limit, actor, action)
    return {"entries": rows, "actors": sorted({r["actor"] for r in rows}),
            "actions": sorted({r["action"] for r in rows}), "approval_min": campaign_approval.approval_min()}


@router.get("/runs/{run_id}")
def run(run_id: str, db: Session = Depends(get_db)):
    """One run in full, with its prompt."""
    r = db.get(AgentRun, run_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return agent_telemetry.as_dict(r, full=True)
