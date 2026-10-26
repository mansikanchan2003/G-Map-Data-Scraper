"""
Qualified and strongly qualified applicants, kept for good.

Every applicant who reaches Qualified (their PIN is in our area and nothing
rules them out) or Strongly qualified (that, plus 12th or more and able to
invest ₹3–5 lakh) is stored in qualified_leads, with why, when, where,
and the nearest SBI branch from our branch list (its code, AO and region).
A later answer that rules them out, or taking the application off the tab,
does not remove them: the list shows where they stand now beside it.

Kept up to date whenever the list is opened: the applications are read
afresh and anyone newly qualified is added, so older applicants are there too.
"""
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.application import ApplicationComment, ApplicationRemoval, QualifiedLead
from src.models.inbox import WhatsAppConversation, WhatsAppMessage
from src.models.sbi_branch import SbiBranch
from src.services import applications, inbox
from src.services import onboarding_bot as bot

QUALIFIED, STRONG = "Qualified", "Strongly qualified"
# A real PIN outside our SBI branch area: kept here too, to reach for another
# proposal such as BT or HDFC (the user, 2026-10-23).
OTHER = applications.NOT_SBI
RANK = {OTHER: 0, QUALIFIED: 1, STRONG: 2}


def level_of(q: dict) -> Optional[str]:
    if q["strongly_qualified"]:
        return STRONG
    if q["pin_qualified"] and not q["not_qualified"]:
        return QUALIFIED
    if q.get("other_proposal"):
        return OTHER
    return None


def why(conv: WhatsAppConversation, q: dict) -> List[str]:
    """Why they qualify, and for Qualified, what is not answered yet."""
    data = conv.bot_data or {}
    coverage = data.get("coverage") or {}
    out = []
    near, km = coverage.get("place"), coverage.get("distance_km")
    if q["pin_qualified"]:
        out.append(f"PIN {coverage.get('pincode')} is in our area"
                   + (f" ({km:g} km from our {near})" if near and km else (f" ({near})" if near else "")))
    elif q.get("other_proposal"):
        out.append(f"PIN {coverage.get('pincode')} is outside our SBI branch area"
                   + (f" ({km:g} km from our nearest, {near})" if near and km else "")
                   + ": for another proposal (BT, HDFC...)")
    edu = data.get("education")
    if edu in ("12", "grad"):
        out.append({"12": "Studied to 12th or a diploma", "grad": "Graduate or post-graduate"}[edu])
    elif edu is None:
        out.append("Education not answered yet")
    if data.get("can_invest") is True:
        out.append("Can invest ₹3–5 lakh")
    elif data.get("can_invest") is None:
        out.append("Investment not answered yet")
    return out


def _candidates(db: Session) -> List[WhatsAppConversation]:
    """Every application from our campaigns, including those taken off the tab."""
    convs = [c for c in db.query(WhatsAppConversation)
             .filter((WhatsAppConversation.bot_step.isnot(None)) | (WhatsAppConversation.documents_submitted_at.isnot(None)))
             .all() if applications.is_application(c)]
    ours = inbox.campaign_phones(db, [c.phone for c in convs])
    return [c for c in convs if c.phone in ours]


def sync(db: Session) -> None:
    """Add anyone newly qualified, raise anyone who went further, and fill in places and branches."""
    convs = _candidates(db)
    typed = applications._typed_pins(db, convs)
    applications._fill_geography(db, convs, typed)
    kept = {r.phone: r for r in db.query(QualifiedLead).all()}
    branches = applications._branches(db)
    # The branch's region (RBO) and circle, which the shared helper leaves out.
    rbo = {b.branch_code: (b.region, b.circle) for b in db.query(SbiBranch.branch_code, SbiBranch.region, SbiBranch.circle)}
    for conv in convs:
        q = applications.qualify(conv)
        level = level_of(q)
        row = kept.get(conv.phone)
        if level is None and row is None:
            continue
        # When they qualified: their last message then, the answer that did it.
        at = inbox.aware(conv.last_message_at) or inbox.now()
        if row is None:
            row = QualifiedLead(phone=conv.phone, level=level, qualified_at=at)
            db.add(row)
            kept[conv.phone] = row
        if level and RANK[level] >= RANK.get(row.level, -1):
            if level == STRONG and not row.strongly_qualified_at:
                row.strongly_qualified_at = at
            row.level, row.why = level, why(conv, q)
        coverage = (conv.bot_data or {}).get("coverage") or {}
        geo = coverage.get("geo") or {}
        # The nearest of our SBI branches, from the PIN's coordinates (kept by the Applications list).
        near = applications._nearest_branch(branches, coverage.get("coords"))
        if near:
            row.branch_code, row.branch_name, row.branch_ao = near["branch_code"], near["branch_name"], near["ao"]
            row.branch_region, row.branch_circle = rbo.get(near["branch_code"], (None, None))
            row.branch_distance_km, row.branch_checked_pin = near["distance_km"], coverage.get("pincode")
        row.name = conv.profile_name or row.name
        row.pincode = coverage.get("pincode") or row.pincode
        row.state, row.district, row.tehsil = (geo.get("state") or row.state, geo.get("district") or row.district,
                                               geo.get("tehsil") or row.tehsil)
    db.commit()


def _iso(value) -> Optional[str]:
    value = inbox.aware(value)
    return value.isoformat() if isinstance(value, datetime) else None


def list_leads(db: Session) -> Dict:
    """Everyone ever qualified, newest first, with where they stand now."""
    sync(db)
    rows = db.query(QualifiedLead).all()
    phones = [r.phone for r in rows]
    convs = {c.phone: c for c in db.query(WhatsAppConversation).filter(WhatsAppConversation.phone.in_(phones))} if phones else {}
    removed = {r.phone for r in db.query(ApplicationRemoval.phone)}
    comments: Dict[str, list] = {}
    for c in (db.query(ApplicationComment).filter(ApplicationComment.phone.in_(phones))
              .order_by(ApplicationComment.created_at).all() if phones else []):
        comments.setdefault(c.phone, []).append(c)
    first_in = dict(db.query(WhatsAppMessage.phone, func.min(WhatsAppMessage.created_at))
                    .filter(WhatsAppMessage.phone.in_(phones), WhatsAppMessage.direction == "IN")
                    .group_by(WhatsAppMessage.phone).all()) if phones else {}
    sources = applications._sources(db, phones)

    items = []
    for r in rows:
        conv = convs.get(r.phone)
        q = applications.qualify(conv) if conv else None
        now_level = level_of(q) if q else None
        items.append({
            "phone": r.phone, "name": r.name, "level": r.level, "why": r.why or [],
            # Where they stand now: their level today, or what ruled them out since.
            "now": now_level or ("Not qualified now: " + ", ".join(q["not_qualified_reasons"]).lower()
                                 if q and q["not_qualified"] else (q["verdict"] if q else "Chat deleted")),
            "still_qualified": bool(now_level),
            "stage": bot.STEP_LABELS.get(conv.bot_step, conv.bot_step or "—") if conv else "—",
            "submitted": bool(conv and conv.documents_submitted_at),
            "submitted_at": _iso(conv.documents_submitted_at) if conv else None,
            "lead_at": _iso(first_in.get(r.phone) or (conv.created_at if conv else None)),
            "qualified_at": _iso(r.qualified_at),
            "strongly_qualified_at": _iso(r.strongly_qualified_at),
            "last_message_at": _iso(conv.last_message_at) if conv else None,
            "pincode": r.pincode, "state": r.state, "district": r.district, "tehsil": r.tehsil,
            "branch": {"code": r.branch_code, "name": r.branch_name, "ao": r.branch_ao, "region": r.branch_region,
                       "circle": r.branch_circle, "distance_km": r.branch_distance_km} if r.branch_code else None,
            "category": (sources.get(r.phone) or {}).get("category"),
            "campaign": (sources.get(r.phone) or {}).get("campaign"),
            "removed": r.phone in removed,
            "comments": [{"comment_id": c.comment_id, "body": c.body, "author": c.author,
                          "created_at": _iso(c.created_at)} for c in comments.get(r.phone, [])],
        })
    items.sort(key=lambda a: a["qualified_at"] or "", reverse=True)
    return {
        "stats": {"total": len(items), "strongly_qualified": sum(a["level"] == STRONG for a in items),
                  "qualified": sum(a["level"] == QUALIFIED for a in items),
                  "other_proposal": sum(a["level"] == OTHER for a in items),
                  "submitted": sum(a["submitted"] for a in items),
                  "dropped": sum(not a["still_qualified"] for a in items)},
        "items": items,
    }
