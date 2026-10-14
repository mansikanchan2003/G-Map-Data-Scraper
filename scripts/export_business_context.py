"""
Export the business context the growth agent needs: how many CSPs are live,
what they earn month by month, how new CSPs ramp up, and how the onboarding
pipeline converts. Written to data/business_context.json for the backend.

Read-only. It reads Tara (Sumit's CSP growth platform, its SQLite database
opened in read-only mode) and the acquisition-pipeline sheets Sumit exports
next to it, and writes only totals and counts: no CSP's name, phone number
or email leaves those files.

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


def csp_sheet(db: sqlite3.Connection, year: int) -> dict:
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
    category = collections.Counter()
    for data, _ in latest.values():
        d = json.loads(data)
        terminal[d.get("Terminal Status") or "Unknown"] += 1
        category[d.get("CSP Category") or "Unknown"] += 1
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
        "csps_in_sheet": len(latest),
        "terminal_status": dict(terminal),
        "category": dict(category.most_common()),
        "commission_by_month": {k: {"csps": v["csps"], "inr": round(v["inr"])} for k, v in sorted(commission.items())},
        "activity_by_month": dict(sorted(activity.items())),
        "new_csps_by_first_month": {k: len(next(iter(v.values()))) for k, v in sorted(cohorts.items()) if k != first_seen},
        "new_csp_ramp": ramp,
        "established_median_txns": established,
    }


def forecasts(db: sqlite3.Connection) -> dict:
    out = {}
    for month, as_of, accrued, projected, txns, ptxns in db.execute(
            """select month, max(as_of), max(accrued_inr), max(projected_inr), max(cum_txns), max(projected_txns)
               from forecast_daily where level = 'business' group by month"""):
        out[month] = {"as_of": as_of, "accrued_inr": round(accrued or 0), "projected_inr": round(projected or 0),
                      "txns": int(txns or 0), "projected_txns": int(ptxns or 0)}
    for month, actual in db.execute("select month, actual_inr from forecast_month where level = 'business'"):
        if actual:
            out.setdefault(month, {})["actual_inr"] = round(actual)
    return out


def pipeline(folder: str) -> dict:
    """The CSP onboarding pipeline: where each applicant stands, and go-lives by month."""
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
            "by_status": dict(status.most_common()),
            "by_state": dict(collections.Counter((r.get("States") or "").strip().title() for r in rows).most_common()),
        }
    path = os.path.join(folder, "pipeline_sheet.csv")
    if os.path.exists(path):
        golive = collections.Counter()
        for r in csv.DictReader(open(path, encoding="utf-8")):
            m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", (r.get("Go Live ") or r.get("Go Live") or "").strip())
            if m:
                golive[f"{m.group(3)}-{int(m.group(2)):02d}"] += 1
        out["go_live_by_month"] = dict(sorted(golive.items()))
    path = os.path.join(folder, "pipeline_target.csv")
    if os.path.exists(path):
        rows = list(csv.DictReader(open(path, encoding="utf-8")))
        out["this_month_by_state"] = [
            {"state": r["State"], "target": int(num(r.get("Target"))), "leads": int(num(r.get("Total Leads"))),
             "cat1": int(num(r.get("CAT 1"))), "cat2": int(num(r.get("CAT 2"))), "go_live": int(num(r.get("Go Live"))),
             "rejected": int(num(r.get("Rejected")))}
            for r in rows if r.get("State")]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tara-db", default="/home/shumit/ORCH_NEW/repo/data/app.db")
    ap.add_argument("--pipeline-dir", default="/home/shumit/dev")
    ap.add_argument("--out", default="data/business_context.json")
    args = ap.parse_args()

    db = sqlite3.connect(f"file:{args.tara_db}?mode=ro", uri=True)
    year = datetime.now().year
    context = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source": "Tara (Sumit's CSP growth platform) and the CSP onboarding pipeline sheets",
        "csp_network": csp_sheet(db, year),
        "revenue_forecasts": forecasts(db),
        "onboarding": pipeline(args.pipeline_dir),
    }
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=1)
    os.replace(tmp, args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
