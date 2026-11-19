"""
The District Coordinators we have, by district (19 Nov 2026): the bot offers a face-to-face
visit by the DC only in these districts, and Biswajit Sir arranges it when someone says yes.

Kept in app_settings under dc_districts as a list of {state, district, dc, phone}, loaded from
the team's sheet (`python -m src.services.dc_network load <file.xlsx|.csv>`: columns State,
District, DC name, DC phone; one row per district a DC covers). Districts are matched by name
as people and India Post write them, so "Ferozpur" and "Firozpur" are one place.
"""
import csv
import json
import re
import sys
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.app_setting import AppSetting

KEY = "dc_districts"

# Districts known by more than one name (TARA's and India Post's among them).
SAME = {
    "sahibzada ajit singh nagar": "mohali", "sas nagar": "mohali", "s a s nagar": "mohali",
    "firozpur": "ferozpur", "ferozepur": "ferozpur", "jyotiba phule nagar": "amroha",
    "gurgaon": "gurugram", "rupnagar": "ropar", "ropar": "ropar", "mewat": "nuh",
    "panchmahals": "panchmahal", "chhota udepur": "chhota udaipur", "ahmadabad": "ahmedabad",
}


def _key(name: Optional[str]) -> str:
    t = re.sub(r"[^a-z ]", " ", (name or "").lower())
    t = re.sub(r"\b(district|dist|distt)\b", " ", t)
    t = " ".join(t.split())
    return SAME.get(t, t)


def load(db: Session) -> List[dict]:
    row = db.query(AppSetting).filter(AppSetting.key == KEY).first()
    try:
        return json.loads(row.value) if row and row.value else []
    except ValueError:
        return []


def save(db: Session, rows: List[dict]) -> int:
    clean = []
    for r in rows:
        district = (r.get("district") or "").strip()
        if not district:
            continue
        clean.append({"state": (r.get("state") or "").strip(), "district": district,
                      "dc": (r.get("dc") or "").strip() or None, "phone": (r.get("phone") or "").strip() or None})
    row = db.query(AppSetting).filter(AppSetting.key == KEY).first()
    if row is None:
        row = AppSetting(key=KEY)
        db.add(row)
    row.value = json.dumps(clean)
    db.commit()
    if clean:
        # The visit offer's templates go to Meta, so it reaches people after 24 hours too.
        try:
            from src.services import nudge_templates
            nudge_templates.submit(db, "dc_visit", "dc_network")
        except Exception:
            pass
    return len(clean)


def dc_for(db: Session, district: Optional[str], state: Optional[str] = None,
           rows: Optional[List[dict]] = None) -> Optional[dict]:
    """The DC for this district, if we have one there."""
    want = _key(district)
    if not want:
        return None
    for r in rows if rows is not None else load(db):
        if _key(r["district"]) == want and (not state or not r.get("state") or _key(r["state"]) == _key(state)):
            return r
    return None


def _rows_from_file(path: str) -> List[dict]:
    """State, District, DC name, DC phone: from an .xlsx (first sheet) or a .csv, headers matched loosely."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
        table = [[("" if v is None else str(v)) for v in row] for row in ws.iter_rows(values_only=True)]
    else:
        with open(path, encoding="utf-8-sig", newline="") as f:
            table = list(csv.reader(f))
    if not table:
        return []
    head = [h.strip().lower() for h in table[0]]

    def col(*words):
        return next((i for i, h in enumerate(head) if any(w in h for w in words)), None)
    s, d = col("state"), col("district")
    n, p = col("dc name", "coordinator", "name"), col("phone", "mobile", "contact", "number")
    if d is None:
        raise ValueError("The sheet needs a District column")
    get = lambda row, i: (row[i].strip() if i is not None and i < len(row) else "")  # noqa: E731
    return [{"state": get(r, s), "district": get(r, d), "dc": get(r, n), "phone": get(r, p)} for r in table[1:]]


def main(argv: List[str]) -> int:
    from src.database import SessionLocal
    if argv[:1] != ["load"] or len(argv) != 2:
        sys.stderr.write("usage: python -m src.services.dc_network load <file.xlsx|file.csv>\n")
        return 2
    db = SessionLocal()
    try:
        n = save(db, _rows_from_file(argv[1]))
        print(f"{n} districts with a DC")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
