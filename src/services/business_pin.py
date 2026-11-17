"""
A business's PIN code (17 Nov 2026), shown in Business Data and its exports.

A business has no PIN of its own. The one in its Google Maps address is the
truest; failing that, the PIN of the place that was searched (a search by PIN
code covers the area around it, so this is the area, not the shop's own).
"""
import re
from typing import Dict, Iterable, Optional

from sqlalchemy.orm import Session

# Indian PIN codes are six digits and never start with 0.
_PIN = re.compile(r"(?<!\d)([1-9]\d{2})\s?(\d{3})(?!\d)")


def from_address(address: Optional[str]) -> Optional[str]:
    """The last PIN code in an address ("..., Rajkot, Gujarat 360001" -> "360001")."""
    hits = _PIN.findall(address or "")
    return "".join(hits[-1]) if hits else None


def searched(db: Session, job_ids: Optional[Iterable[str]] = None) -> Dict[str, str]:
    """Job id -> the PIN code its search was for, where the place has a real one."""
    from src.models import Job, Location
    q = db.query(Job.job_id, Location.pincode).join(Location, Location.location_id == Job.location_id)
    if job_ids is not None:
        ids = list({j for j in job_ids if j})
        if not ids:
            return {}
        q = q.filter(Job.job_id.in_(ids))
    return {j: p for j, p in q if p and re.fullmatch(r"[1-9]\d{5}", p.strip())}


def pin_for(biz, by_job: Dict[str, str]) -> Optional[str]:
    return from_address(getattr(biz, "address", None)) or by_job.get(getattr(biz, "job_id", None))
