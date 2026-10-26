"""
The Agent quality page: how AutoGMap's agents are doing (agent_telemetry.py),
and each run's full chain, with the context it used, for the "why".
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.database import get_db
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
def runs(agent: Optional[str] = None, outcome: Optional[str] = None, limit: int = Query(50, ge=1, le=500),
         db: Session = Depends(get_db)):
    """The latest runs, newest first: output, final version, edit distance and the context used."""
    return agent_telemetry.recent(db, agent, outcome, limit)


@router.get("/runs/{run_id}")
def run(run_id: str, db: Session = Depends(get_db)):
    """One run in full, with its prompt."""
    r = db.get(AgentRun, run_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return agent_telemetry.as_dict(r, full=True)
