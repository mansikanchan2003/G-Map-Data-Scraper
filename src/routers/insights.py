"""
Campaign Insights: how each campaign did, what might have made the difference,
and the playbook learned across all of them.

Reports are saved per campaign and a playbook snapshot is written after each
one, so what has been learned is kept, not just recomputed. /playbook is the
machine-readable version, for a template agent to use as its reference.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.insights import CampaignInsight, InsightSnapshot
from src.models.user import User
from src.models.whatsapp import WhatsAppCampaign
from src.routers.auth import current_user
from src.services import campaign_insights as ci

router = APIRouter(prefix="/api/v1/whatsapp/insights", tags=["Campaign Insights"])

# Meta keeps reporting deliveries and reads for days, so recent campaigns are
# recomputed when their saved report is older than this.
STALE_AFTER = timedelta(minutes=30)
RECENT = timedelta(days=14)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.get("/dimensions")
def dimensions():
    return {"groups": ci.GROUPS,
            "dimensions": [{"key": k, **v} for k, v in ci.DIMENSIONS.items()],
            "min_sent": ci.MIN_SENT}


@router.get("/playbook")
def get_playbook(db: Session = Depends(get_db)):
    """What works best so far — the reference for writing the next template."""
    return ci.playbook(db)


@router.get("/explore")
def explore(
    dims: str = Query(..., description="Comma-separated dimension keys, up to 3"),
    min_sent: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """Any dimension, or any combination of up to three, ranked by response."""
    keys = [d.strip() for d in dims.split(",") if d.strip()]
    unknown = [k for k in keys if k not in ci.DIMENSIONS]
    if unknown or not keys or len(keys) > 3:
        raise HTTPException(status_code=400,
                            detail=f"Choose 1–3 of: {', '.join(ci.DIMENSIONS)}" +
                                   (f" (unknown: {', '.join(unknown)})" if unknown else ""))
    facts = ci.load_facts(db)
    outcome = ci.judged_on(facts)
    return {"dims": keys, "judged_on": outcome, "overall": ci._stats(facts, outcome) if facts else None,
            "rows": ci.aggregate(facts, tuple(keys), min_sent=min_sent, outcome=outcome)[:200]}


@router.get("/campaigns")
def list_campaign_insights(db: Session = Depends(get_db)):
    """Every finished campaign with its saved report, refreshing recent stale ones."""
    campaigns = (
        db.query(WhatsAppCampaign)
        .filter(WhatsAppCampaign.status.in_(("COMPLETED", "PARTIAL", "FAILED", "CANCELLED")))
        .order_by(WhatsAppCampaign.created_at.desc())
        .all()
    )
    saved = {i.campaign_id: i for i in db.query(CampaignInsight).all()}
    now = datetime.now(timezone.utc)

    book = None
    for c in campaigns:
        row = saved.get(c.campaign_id)
        recent = _aware(c.created_at) and now - _aware(c.created_at) < RECENT
        stale = row is None or (recent and now - _aware(row.computed_at) > STALE_AFTER)
        if stale and (c.successful_count or 0) > 0:
            book = book or ci.playbook(db)
            saved[c.campaign_id], _ = ci.refresh_campaign(db, c.campaign_id, book)

    out = []
    for c in campaigns:
        row = saved.get(c.campaign_id)
        m = (row.metrics if row else None) or {}
        out.append({
            "campaign_id": c.campaign_id,
            "name": c.name,
            "is_test": (c.total_contacts or 0) < ci.TEST_CAMPAIGN_MAX,
            "status": c.status,
            "created_at": c.created_at,
            "sent": m.get("sent", c.successful_count or 0),
            "delivered": m.get("delivered"),
            "read": m.get("read"),
            "responded": m.get("responded"),
            "response_rate": m.get("response_rate"),
            "tracked": m.get("tracked"),
            "vs_all_campaigns": row.vs_all_campaigns if row else None,
            "headline": _headline(row.suggestions if row else None),
            "computed_at": row.computed_at if row else None,
        })
    return out


def _headline(suggestions) -> Optional[str]:
    """The most useful single line for the campaign list."""
    if not suggestions:
        return None
    order = {"strong": 0, "likely": 1, "no_difference": 2, "too_early": 3}
    kinds = {"strength": 0, "opportunity": 1, "weakness": 2, "warning": 3, "info": 4}
    best = sorted(suggestions, key=lambda s: (order.get(s["confidence"], 9), kinds.get(s["kind"], 9)))[0]
    return best["message"]


@router.get("/campaigns/{campaign_id}")
def campaign_insight(campaign_id: str, db: Session = Depends(get_db)):
    try:
        _, report = ci.refresh_campaign(db, campaign_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return report


@router.get("/history")
def history(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    """What the playbook concluded after each campaign, newest first."""
    snaps = db.query(InsightSnapshot).order_by(InsightSnapshot.created_at.desc()).limit(limit).all()
    names = {c.campaign_id: c.name for c in db.query(WhatsAppCampaign).filter(
        WhatsAppCampaign.campaign_id.in_([s.campaign_id for s in snaps if s.campaign_id])).all()}
    return [{
        "snapshot_id": s.snapshot_id, "created_at": s.created_at, "trigger": s.trigger,
        "campaign": names.get(s.campaign_id), "campaigns": s.campaigns,
        "recipients": s.recipients, "responses": s.responses, "playbook": s.playbook,
    } for s in snaps]


@router.post("/snapshot")
def take_snapshot(db: Session = Depends(get_db)):
    """Records the playbook now — used to seed the history from past campaigns."""
    snap = ci.record_snapshot(db, "manual")
    return {"snapshot_id": snap.snapshot_id, "campaigns": snap.campaigns, "recipients": snap.recipients}


@router.get("/growth")
def growth(db: Session = Depends(get_db)):
    """
    The lead goal, where people drop out on the way to a lead, and what to do
    next: who to call, where and whom to message, what to make.
    """
    from src.services import growth_plan
    return growth_plan.plan(db)


# --- Questions to Kiosk KAI, from the Plan tab ----------------------------------

class Question(BaseModel):
    question: str = Field(..., min_length=3, max_length=600)


@router.get("/ask")
def ask_status():
    """Whether questions can be asked here, and Kiosk KAI's own chat page."""
    from src.services import kiosk_kai
    return {"enabled": kiosk_kai.configured(), "chat_url": kiosk_kai.CHAT_URL,
            "left_today": kiosk_kai.asks_left(), "daily_max": kiosk_kai.ask_daily_max()}


@router.post("/ask")
def ask(req: Question, user: User = Depends(current_user)):
    """
    Asks Kiosk KAI about AutoGMap, the application form or TARA's revenue.
    Answers take up to a few minutes, so this returns at once with an id.
    """
    from src.services import kiosk_kai
    try:
        return kiosk_kai.ask(req.question.strip(), user.user_id)
    except kiosk_kai.AskRefused as e:
        raise HTTPException(status_code=429 if kiosk_kai.configured() else 503, detail=str(e))


@router.get("/ask/{ask_id}")
def asked(ask_id: str, user: User = Depends(current_user)):
    from src.services import kiosk_kai
    out = kiosk_kai.asked(ask_id, user.user_id)
    if out is None:
        raise HTTPException(status_code=404, detail="That question is no longer here. Ask it again.")
    return out


class RevenueGoal(BaseModel):
    # A total to earn between two dates; an empty amount clears the goal.
    inr: Optional[int] = Field(None, ge=0, description="The total in rupees")
    start: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="e.g. 2026-10-15")
    end: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="e.g. 2026-12-31")


@router.get("/revenue-goal")
def get_revenue_goal(db: Session = Depends(get_db)):
    """The team's revenue goal: a total to earn between two dates. The growth agent reads it."""
    from src.services import business_context
    return business_context.revenue_goal(db)


@router.put("/revenue-goal")
def put_revenue_goal(req: RevenueGoal, db: Session = Depends(get_db)):
    from src.services import business_context
    if req.inr and not (req.start and req.end):
        raise HTTPException(status_code=400, detail="A goal needs a start and an end date")
    try:
        return business_context.set_revenue_goal(db, req.inr, req.start, req.end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/dispositions")
def disposition_mix(db: Session = Depends(get_db)):
    """Where the people each campaign, template and state reached stand now, by disposition."""
    from src.services import lead_journey
    return lead_journey.disposition_mix(db)
