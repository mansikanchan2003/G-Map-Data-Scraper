"""
How Eko earns from a CSP, from onboarding to revenue, in numbers the growth
agent can reason with, and the lead goal the agent sets itself from them.

The numbers come from data/business_context.json, which
scripts/export_business_context.py writes on the host from Tara (Sumit's CSP
growth platform) and the onboarding pipeline sheets: totals only, no CSP's
personal details. Without that file the agent still works, from AutoGMap's
own results alone.

THE PROCESS, as the agent is told it:
 1. AutoGMap messages businesses; some tap Interested and qualify (area,
    12th pass, can invest ₹5 lakh) and submit documents. That is a LEAD.
 2. The onboarding team takes the lead through CAT-1 and CAT-2: documents,
    then digital and hard-copy approval by the SBI branch, RBO and LHO, and
    the BC-CSP agreement. Many are rejected here, mostly on hard copies.
 3. Approved, the CSP goes live and starts transacting.
 4. A new CSP ramps up slowly: a fraction of an established CSP's
    transactions in the first months.
 5. Revenue is earned per transaction, so it follows the transactions of
    every live CSP. New CSPs add to it gradually; the existing network's
    activity moves it most in any one month.

THE GOAL: each month the agent works out how many new CSPs usually go live,
aims to add half as many again through AutoGMap leads, and turns that into
leads with the share of decided applicants who go live. It says why, and
what the extra CSPs should earn, so the goal can be checked against reality.
"""
import json
import math
import os
from datetime import date
from typing import Dict, List, Optional

CONTEXT_FILE = os.environ.get("BUSINESS_CONTEXT_FILE", os.path.join("data", "business_context.json"))
# AutoGMap aims to add this share to the CSPs going live each month.
GROWTH_SHARE = 0.5
# Without business data, a modest goal from AutoGMap's own results.
FALLBACK_LEADS = 3

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load() -> Optional[dict]:
    try:
        with open(CONTEXT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _key(label: str) -> str:
    """'Sep-26' -> '2026-09'."""
    mon, yy = label.split("-")
    return f"20{yy}-{MONTH_NAMES.index(mon) + 1:02d}"


def label(key: str) -> str:
    """'2026-09' -> 'Sep 2026'."""
    y, m = key.split("-")
    return f"{MONTH_NAMES[int(m) - 1]} {y}"


def summarise(ctx: dict) -> dict:
    """The process in numbers: revenue by month, what a CSP earns, how new ones ramp, how applicants convert."""
    net = ctx.get("csp_network") or {}
    fc = {_key(k): v for k, v in (ctx.get("revenue_forecasts") or {}).items()}
    onboarding = ctx.get("onboarding") or {}
    activity = net.get("activity_by_month") or {}
    commission = net.get("commission_by_month") or {}

    # Revenue per transaction, from the latest month with both.
    rpt = None
    for k in sorted(fc, reverse=True):
        v = fc[k]
        if v.get("actual_inr") and v.get("txns"):
            rpt = v["actual_inr"] / v["txns"]
            break
    if rpt is None:
        for k in sorted(commission, reverse=True):
            if k in activity and activity[k]["txns"]:
                rpt = commission[k]["inr"] / activity[k]["txns"]
                break

    # New CSPs per month: the more complete of Tara's first transactions and the go-live sheet.
    # Tara's first month cannot tell new CSPs from old ones, so it and the
    # months before it are unknown rather than zero.
    first_tara = min(activity) if activity else None
    new = {k: 0 for k in activity if k != first_tara}
    new.update(net.get("new_csps_by_first_month") or {})
    for k, n in (onboarding.get("go_live_by_month") or {}).items():
        new[k] = max(new.get(k, 0), n)

    months = sorted(set(activity) | set(commission) | set(fc))
    table = []
    for k in months:
        revenue, basis = None, None
        if fc.get(k, {}).get("actual_inr"):
            revenue, basis = fc[k]["actual_inr"], "actual"
        elif k in commission:
            revenue, basis = commission[k]["inr"], "actual"
        elif fc.get(k, {}).get("projected_inr"):
            revenue, basis = fc[k]["projected_inr"], "projected"
        elif k in activity and rpt:
            revenue, basis = round(activity[k]["txns"] * rpt), "estimated"
        table.append({
            "month": k, "label": label(k),
            "active_csps": (activity.get(k) or commission.get(k) or {}).get("csps"),
            "transactions": (activity.get(k) or {}).get("txns"),
            "revenue_inr": revenue, "revenue_basis": basis,
            "new_csps": new.get(k),
        })

    # How a new CSP ramps: median transactions in its 1st, 2nd... month, averaged over cohorts.
    ramp_by_age: Dict[int, List[int]] = {}
    for start, months_ in (net.get("new_csp_ramp") or {}).items():
        for i, k in enumerate(sorted(months_)):
            ramp_by_age.setdefault(i + 1, []).append(months_[k]["median_txns"])
    ramp = [{"month": age, "median_txns": round(sum(v) / len(v)),
             "revenue_inr": round(sum(v) / len(v) * rpt) if rpt else None}
            for age, v in sorted(ramp_by_age.items())]
    established = net.get("established_median_txns") or {}
    full = [v for k, v in sorted(established.items()) if fc.get(k, {}).get("actual_inr") or k in commission
            or (k in activity and k != max(activity))]
    mature_txns = round(sum(full) / len(full)) if full else None

    apps = onboarding.get("applicants") or {}
    decided = (apps.get("went_live") or 0) + (apps.get("rejected") or 0)
    go_live_rate = apps["went_live"] / decided if decided else None

    # How much of a month's revenue came from CSPs that went live recently.
    contribution = []
    for row in table:
        if not row["revenue_inr"] or not rpt:
            continue
        recent = 0.0
        for start, months_ in (net.get("new_csp_ramp") or {}).items():
            m = months_.get(row["month"])
            if m:
                recent += m["csps"] * m["median_txns"] * rpt
        contribution.append({"month": row["month"], "label": row["label"], "from_new_csps_inr": round(recent),
                             "share": round(recent / row["revenue_inr"], 4)})

    complete = [r for r in table if r["revenue_basis"] == "actual"]
    change = None
    if len(complete) >= 2:
        a, b = complete[-2], complete[-1]
        new_part = next((c["from_new_csps_inr"] for c in contribution if c["month"] == b["month"]), 0)
        change = {"from": a["label"], "to": b["label"], "revenue_change_inr": b["revenue_inr"] - a["revenue_inr"],
                  "csp_change": (b["active_csps"] or 0) - (a["active_csps"] or 0),
                  "from_new_csps_inr": new_part}

    return {
        "exported_at": ctx.get("exported_at"),
        "months": table,
        "revenue_per_txn": round(rpt, 2) if rpt else None,
        "mature_csp": {"median_txns": mature_txns, "revenue_inr": round(mature_txns * rpt) if mature_txns and rpt else None},
        "new_csp_ramp": ramp,
        "new_csps_contribution": contribution,
        "latest_change": change,
        "csps_live": (net.get("terminal_status") or {}).get("Active"),
        "csps_inactive": (net.get("terminal_status") or {}).get("Inactive"),
        "onboarding": {
            "applicants": apps.get("total"), "went_live": apps.get("went_live"), "rejected": apps.get("rejected"),
            "in_progress": apps.get("in_progress"),
            "go_live_rate": round(go_live_rate, 3) if go_live_rate else None,
            "top_rejections": [(s, n) for s, n in (apps.get("by_status") or {}).items() if "reject" in s.lower()][:4],
        },
        "this_month_by_state": onboarding.get("this_month_by_state") or [],
    }


def agent_goal(summary: Optional[dict], our_states: List[str], today: date) -> dict:
    """The lead goal for this calendar month, with the reasoning behind it."""
    month_end = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    period = {"start": date(today.year, today.month, 1).isoformat(), "end": month_end.isoformat(),
              "label": f"{MONTH_NAMES[today.month - 1]} {today.year}"}
    if not summary:
        return {**period, "leads": FALLBACK_LEADS, "set_by": "agent", "basis": "own results only",
                "reasoning": ["No business data from Tara yet, so a modest goal from AutoGMap's own results."]}

    recent = [r for r in summary["months"] if r["month"] < today.strftime("%Y-%m") and r["new_csps"] is not None][-3:]
    baseline = sum(r["new_csps"] for r in recent) / len(recent) if recent else 0
    extra = max(1, math.ceil(baseline * GROWTH_SHARE))
    rate = summary["onboarding"]["go_live_rate"] or 0.5
    leads = math.ceil(extra / rate)

    mine = {s.lower() for s in our_states}
    gaps = [{"state": r["state"], "target": r["target"], "leads": r["leads"], "gap": max(r["target"] - r["leads"], 0)}
            for r in summary["this_month_by_state"] if r["state"].lower() in mine]
    gap_total = sum(g["gap"] for g in gaps)

    ramp = {r["month"]: r for r in summary["new_csp_ramp"]}
    m2 = (ramp.get(2) or ramp.get(1) or {}).get("revenue_inr")
    mature = summary["mature_csp"]["revenue_inr"]
    latest = summary["months"][-1] if summary["months"] else None
    lately = ", ".join(f"{r['label']}: {r['new_csps']}" for r in recent)
    reasoning = [
        f"About {baseline:.1f} new CSPs went live a month lately ({lately}).",
        f"AutoGMap aims to add half as many again: {extra} more CSP{'s' if extra != 1 else ''} live a month.",
        f"{round(rate * 100)}% of decided applicants go live (the rest are rejected, mostly on hard copies "
        f"at the branch or LHO), so {extra} more need {leads} leads with correct documents.",
    ]
    if m2 and mature:
        reasoning.append(
            f"Each new CSP earns about ₹{m2:,.0f} in its second month and nears ₹{mature:,.0f} a month once "
            f"established, so the extra CSPs add about ₹{extra * m2:,.0f} soon and ₹{extra * mature:,.0f} a month "
            f"later" + (f", against {latest['label']}'s ₹{latest['revenue_inr'] / 1e5:.1f} lakh." if latest and latest['revenue_inr'] else "."))
    if gaps:
        reasoning.append("The onboarding team's targets this month in our states: " + "; ".join(
            f"{g['state']} {g['leads']} leads of {g['target']}" for g in gaps)
            + f". A gap of {gap_total} applicants that our leads can fill.")
    return {**period, "leads": leads, "extra_csps": extra, "baseline_new_csps": round(baseline, 1),
            "go_live_rate": rate, "set_by": "agent", "basis": "business data from Tara",
            "state_gaps": gaps, "stretch": gap_total, "reasoning": reasoning}


def process_text(summary: Optional[dict]) -> str:
    """The whole process, told to an agent in a paragraph with the numbers in it."""
    if not summary:
        return ("HOW EKO EARNS: a lead (documents submitted) goes through onboarding checks and SBI approvals, "
                "goes live as a CSP, and earns Eko revenue on every transaction it makes.")
    s = summary
    ob = s["onboarding"]
    ramp = ", ".join(f"month {r['month']}: ~{r['median_txns']} transactions" for r in s["new_csp_ramp"][:3])
    months = "; ".join(f"{r['label']}: {r['active_csps']} CSPs, ₹{(r['revenue_inr'] or 0) / 1e5:.1f} lakh"
                       f"{' (' + r['revenue_basis'] + ')' if r['revenue_basis'] != 'actual' else ''}"
                       for r in s["months"][-4:])
    ch = s["latest_change"]
    change = (f" From {ch['from']} to {ch['to']} revenue moved by ₹{ch['revenue_change_inr'] / 1e5:+.1f} lakh while the "
              f"number of CSPs changed by {ch['csp_change']:+d}; new CSPs brought only ₹{ch['from_new_csps_inr']:,}. "
              "So in any one month revenue follows the existing CSPs' activity; new CSPs add to it over months."
              if ch else "")
    return (
        f"HOW EKO EARNS, from a lead to revenue. A lead (documents submitted) goes to the onboarding team: CAT-1, "
        f"CAT-2, digital and hard-copy approval by the SBI branch, RBO and LHO, then the BC-CSP agreement. Of "
        f"{ob['applicants']} applicants, {ob['went_live']} went live and {ob['rejected']} were rejected "
        f"({round((ob['go_live_rate'] or 0) * 100)}% of those decided went live); most rejections are hard copies "
        f"refused by the branch or LHO, so complete, correct documents matter. A live CSP earns Eko about "
        f"₹{s['revenue_per_txn']} per transaction; an established one makes ~{s['mature_csp']['median_txns']} "
        f"transactions (₹{(s['mature_csp']['revenue_inr'] or 0):,}) a month, a new one far fewer at first ({ramp}). "
        f"The network: {months}.{change}"
    )
