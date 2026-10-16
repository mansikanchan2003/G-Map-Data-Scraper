"""
Export the business context the growth agent needs: how many CSPs are live,
what they earn month by month, how new CSPs ramp up, and how the onboarding
pipeline converts. Written to data/business_context.json for the backend.

Read-only. It reads Tara (Sumit's CSP growth platform, its SQLite database
opened in read-only mode) and the acquisition-pipeline sheets Sumit exports
next to it, and writes only totals and counts: no CSP's name, phone number
or email leaves those files.

Only what the team asked for (2026-10-14/16), and nothing else: for the last
three months and this one, how many CSPs went live, the revenue they made,
how the new CSPs added to it, and how applicants get from documents to going
live. No CSP tiers, no state targets, no per-status or per-state breakdowns.

Runs on the host, where those files are, not in the container:

    python3 scripts/export_business_context.py \
        --tara-db /home/shumit/ORCH_NEW/repo/data/app.db \
        --pipeline-dir /home/shumit/dev \
        --out data/business_context.json
"""
import argparse
import collections
import csv
import json
import os
import re
import sqlite3
import statistics
from datetime import datetime, timezone

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LONG = {"Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April", "May": "May", "Jun": "June",
        "Jul": "July", "Aug": "August", "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December"}


def num(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError):
        return 0.0


def month_key(label: str, year: int) -> str:
    return f"{year}-{MONTHS.index(label) + 1:02d}"


def window_start(today: datetime) -> str:
    """The first month kept: three months before this one ("2026-07" in October)."""
    y, m = today.year, today.month - 3
    if m < 1:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


def csp_sheet(db: sqlite3.Connection, year: int, since: str) -> dict:
    """Per month: CSPs earning and their commission, CSPs transacting and transactions; and the ramp of new CSPs."""
    latest = {}
    for ref, data, synced in db.execute("select external_ref, data, synced_at from csp_sheet_snapshot"):
        if ref not in latest or synced > latest[ref][1]:
            latest[ref] = (data, synced)
    yy = str(year)[-2:]
    commission = collections.defaultdict(lambda: {"csps": 0, "inr": 0.0})
    activity = collections.defaultdict(lambda: {"csps": 0, "txns": 0})
    cohorts = collections.defaultdict(lambda: collections.defaultdict(list))
    terminal = collections.Counter()
    for data, _ in latest.values():
        d = json.loads(data)
        terminal[d.get("Terminal Status") or "Unknown"] += 1
        for m in MONTHS:
            v = num(d.get(f"CSP Commission :: {m}'{yy}"))
            if v > 0:
                commission[month_key(m, year)]["csps"] += 1
                commission[month_key(m, year)]["inr"] += v
        first = None
        for m in MONTHS:
            v = num(d.get(f"Total Transaction Count {LONG[m]}'{yy}"))
            if v > 0:
                key = month_key(m, year)
                activity[key]["csps"] += 1
                activity[key]["txns"] += int(v)
                first = first or key
                cohorts[first][key].append(v)
    first_seen = min(cohorts) if cohorts else None
    # CSPs whose first transactions came after the sheet's first month are new.
    ramp = {}
    for start, months in cohorts.items():
        if start == first_seen:
            continue
        ramp[start] = {m: {"csps": len(v), "median_txns": round(statistics.median(v))} for m, v in sorted(months.items())}
    established = {m: round(statistics.median(v)) for m, v in sorted(cohorts.get(first_seen, {}).items())}
    return {
        # How many CSPs are live now (the network's size), not who they are.
        "terminal_status": {k: terminal[k] for k in ("Active", "Inactive") if k in terminal},
        "commission_by_month": {k: {"csps": v["csps"], "inr": round(v["inr"])}
                                for k, v in sorted(commission.items()) if k >= since},
        "activity_by_month": {k: v for k, v in sorted(activity.items()) if k >= since},
        "new_csps_by_first_month": {k: len(next(iter(v.values()))) for k, v in sorted(cohorts.items())
                                    if k != first_seen and k >= since},
        "new_csp_ramp": {k: v for k, v in ramp.items() if k >= since},
        "established_median_txns": {k: v for k, v in established.items() if k >= since},
    }


def forecasts(db: sqlite3.Connection, since: str) -> dict:
    """Revenue by month: so far this month (accrued), projected, and actual once closed."""
    out = {}
    for month, as_of, accrued, projected, txns, ptxns in db.execute(
            """select month, max(as_of), max(accrued_inr), max(projected_inr), max(cum_txns), max(projected_txns)
               from forecast_daily where level = 'business' group by month"""):
        out[month] = {"as_of": as_of, "accrued_inr": round(accrued or 0), "projected_inr": round(projected or 0),
                      "txns": int(txns or 0), "projected_txns": int(ptxns or 0)}
    for month, actual in db.execute("select month, actual_inr from forecast_month where level = 'business'"):
        if actual:
            out.setdefault(month, {})["actual_inr"] = round(actual)
    return {k: v for k, v in out.items()
            if "-" in k and k.split("-")[0] in MONTHS and month_key(k.split("-")[0], 2000 + int(k.split("-")[1])) >= since}


def pipeline(folder: str, since: str) -> dict:
    """The onboarding pipeline in totals: applicants live, rejected and in progress; go-lives by month."""
    out = {}
    path = os.path.join(folder, "gsheet_leads.csv")
    if os.path.exists(path):
        rows = list(csv.DictReader(open(path, encoding="utf-8")))
        status = collections.Counter((r.get("CAT-2 Status") or "Not started").strip() for r in rows)
        live = sum(n for s, n in status.items() if "go live" in s.lower())
        rejected = sum(n for s, n in status.items() if "reject" in s.lower())
        out["applicants"] = {
            "total": len(rows), "went_live": live, "rejected": rejected,
            "in_progress": len(rows) - live - rejected,
        }
    path = os.path.join(folder, "pipeline_sheet.csv")
    if os.path.exists(path):
        golive = collections.Counter()
        for r in csv.DictReader(open(path, encoding="utf-8")):
            m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", (r.get("Go Live ") or r.get("Go Live") or "").strip())
            if m:
                golive[f"{m.group(3)}-{int(m.group(2)):02d}"] += 1
        out["go_live_by_month"] = {k: v for k, v in sorted(golive.items()) if k >= since}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tara-db", default="/home/shumit/ORCH_NEW/repo/data/app.db")
    ap.add_argument("--pipeline-dir", default="/home/shumit/dev")
    ap.add_argument("--out", default="data/business_context.json")
    args = ap.parse_args()

    db = sqlite3.connect(f"file:{args.tara_db}?mode=ro", uri=True)
    year = datetime.now().year
    since = window_start(datetime.now())
    context = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source": "Tara (Sumit's CSP growth platform) and the CSP onboarding pipeline sheets",
        "since": since,
        "csp_network": csp_sheet(db, year, since),
        "revenue_forecasts": forecasts(db, since),
        "onboarding": pipeline(args.pipeline_dir, since),
    }
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=1)
    os.replace(tmp, args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
