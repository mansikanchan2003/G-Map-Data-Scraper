"""
The nudges as Meta templates, for when someone's 24-hour window is shut.

One template per purpose and language, named eko_nudge_<purpose> (Hindi in
Latin letters as eko_nudge_<purpose>_hinglish, registered as English, since
Meta has no code for it). Nothing goes to Meta until someone presses Submit
in the Dispositions tab: the team reviews the words first (2026-10-21). Each
submitted one is a template row with origin "nudge", kept out of the
campaign template list; its review state comes back from Meta like any
other template's.
"""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.whatsapp import WhatsAppTemplate
from src.services import creative_brief, nudge_messages
from src.services.nudge_messages import HINGLISH

ORIGIN = "nudge"
# Utility: each one follows up something the person asked for or started.
CATEGORY = "UTILITY"


def meta_name(purpose: str, variant: str) -> str:
    return f"eko_nudge_{purpose}" + ("_hinglish" if variant == HINGLISH else "")


def meta_lang(variant: str) -> str:
    return "en" if variant in ("en", HINGLISH) else (creative_brief.meta_language(variant) or variant)


def _local_name(purpose: str, variant: str) -> str:
    return f"nudge_{purpose}_{variant}"


def _rows(db: Session) -> Dict[str, WhatsAppTemplate]:
    return {t.name: t for t in db.query(WhatsAppTemplate).filter(WhatsAppTemplate.origin == ORIGIN).all()}


def approved(db: Session, purpose: str, variant: str) -> Optional[WhatsAppTemplate]:
    """The approved template for a nudge, or None while there is none."""
    row = _rows(db).get(_local_name(purpose, variant))
    return row if row and (row.status or "").upper() == "APPROVED" else None


def listing(db: Session) -> List[dict]:
    """Every nudge in every language, with its words and where it stands with Meta."""
    rows = _rows(db)
    out = []
    for purpose, about in nudge_messages.PURPOSES.items():
        variants = []
        for v in nudge_messages.VARIANTS:
            row = rows.get(_local_name(purpose, v))
            variants.append({"variant": v, "text": nudge_messages.text(purpose, v),
                             "meta_name": meta_name(purpose, v), "meta_language": meta_lang(v),
                             "status": (row.status if row else "NOT_SUBMITTED").upper()})
        out.append({"purpose": purpose, "about": about, "variants": variants})
    return out


def submit(db: Session, purpose: str, by: str) -> List[dict]:
    """
    Send one purpose's templates, every language, to Meta for review.
    Languages already submitted are left as they are.
    """
    from src.services.whatsapp_service import WhatsAppTemplateSubmissionService

    if purpose not in nudge_messages.PURPOSES:
        raise ValueError(f"Unknown nudge: {purpose}")
    rows = _rows(db)
    service = WhatsAppTemplateSubmissionService(db)
    results = []
    for v in nudge_messages.VARIANTS:
        name = _local_name(purpose, v)
        row = rows.get(name)
        if row and (row.status or "").upper() not in ("NOT_SUBMITTED", "REJECTED", "FAILED", "DRAFT"):
            results.append({"variant": v, "status": row.status})
            continue
        if row is None:
            import uuid
            row = WhatsAppTemplate(template_id=uuid.uuid4().hex, name=name, status="Draft",
                                   meta_template_name=meta_name(purpose, v), language_code=meta_lang(v),
                                   category=CATEGORY, header_type="NONE", body=nudge_messages.text(purpose, v),
                                   origin=ORIGIN, reviewed_by=by)
            db.add(row)
            db.flush()
        else:
            row.body = nudge_messages.text(purpose, v)
        result = service.submit(row, CATEGORY)
        if result.get("status") != "success":
            row.status = "FAILED"
            row.review_note = (result.get("error") or "")[:1000]
        db.commit()
        results.append({"variant": v, "status": row.status, "error": result.get("error")})
    return results


def refresh(db: Session) -> None:
    """Bring the submitted nudges' review states up to date from Meta."""
    from src.services.sheet_templates import refresh_statuses

    rows = [t for t in _rows(db).values() if (t.status or "").upper() not in ("APPROVED", "FAILED", "DRAFT")]
    if rows:
        refresh_statuses(db, rows)
