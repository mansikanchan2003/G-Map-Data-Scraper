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


# The utility wording of a nudge (nudge_messages.UTILITY_TEXT) goes to Meta as its own
# template, eko_nudge_<purpose>_v2, so the approved one already in use stays as it is.
V2 = "_v2"


def keys() -> List[str]:
    """Every template set the team can submit: each nudge, then each nudge's utility wording."""
    return list(nudge_messages.PURPOSES) + [p + V2 for p in nudge_messages.UTILITY_TEXT]


def _base(key: str) -> str:
    return key[:-len(V2)] if key.endswith(V2) else key


def _text(key: str, variant: str) -> Optional[str]:
    """The words of a template set in a language; None where the utility wording has none."""
    if key.endswith(V2):
        return nudge_messages.UTILITY_TEXT.get(_base(key), {}).get(variant)
    return nudge_messages.text(key, variant)


def _ok(row: Optional[WhatsAppTemplate]) -> bool:
    return bool(row) and (row.status or "").upper() == "APPROVED"


def approved(db: Session, purpose: str, variant: str) -> Optional[WhatsAppTemplate]:
    """
    The approved template for a nudge, or None while there is none. The utility
    wording comes first, but only once Meta has approved it as UTILITY: one Meta
    filed as Marketing is no better than the template already in use.
    """
    rows = _rows(db)
    v2 = rows.get(_local_name(purpose + V2, variant))
    if _ok(v2) and (v2.category or "").upper() == CATEGORY:
        return v2
    row = rows.get(_local_name(purpose, variant))
    return row if _ok(row) else None


def listing(db: Session) -> List[dict]:
    """Every nudge in every language, with its words and where it stands with Meta."""
    rows = _rows(db)
    out = []
    for key in keys():
        base = _base(key)
        about = nudge_messages.PURPOSES[base] + (" · Utility wording (v2)" if key != base else "")
        variants = []
        for v in nudge_messages.VARIANTS:
            text = _text(key, v)
            if text is None:
                continue
            row = rows.get(_local_name(key, v))
            variants.append({"variant": v, "text": text,
                             "meta_name": meta_name(key, v), "meta_language": meta_lang(v),
                             "status": (row.status if row else "NOT_SUBMITTED").upper(),
                             "category": (row.category or "").upper() if row else None})
        out.append({"purpose": key, "about": about, "variants": variants, "utility_v2": key != base})
    return out


def submit(db: Session, purpose: str, by: str) -> List[dict]:
    """
    Send one purpose's templates, every language, to Meta for review.
    Languages already submitted are left as they are.
    """
    from src.services.whatsapp_service import WhatsAppTemplateSubmissionService

    if purpose not in keys():
        raise ValueError(f"Unknown nudge: {purpose}")
    v2 = purpose.endswith(V2)
    rows = _rows(db)
    service = WhatsAppTemplateSubmissionService(db)
    results = []
    for v in nudge_messages.VARIANTS:
        text = _text(purpose, v)
        if text is None:
            continue
        name = _local_name(purpose, v)
        row = rows.get(name)
        if row and (row.status or "").upper() not in ("NOT_SUBMITTED", "REJECTED", "FAILED", "DRAFT"):
            results.append({"variant": v, "status": row.status})
            continue
        if row is None:
            import uuid
            row = WhatsAppTemplate(template_id=uuid.uuid4().hex, name=name, status="Draft",
                                   meta_template_name=meta_name(purpose, v), language_code=meta_lang(v),
                                   category=CATEGORY, header_type="NONE", body=text,
                                   origin=ORIGIN, reviewed_by=by)
            db.add(row)
            db.flush()
        else:
            row.body = text
        result = service.submit(row, CATEGORY)
        theirs = _category_meta_has(result)
        if theirs and theirs != CATEGORY and v2:
            # The utility wording exists to be Utility; filed as Marketing it is no use.
            result = {"status": "error", "error": f"Meta files this template as {theirs}, not Utility"}
        elif theirs and theirs != CATEGORY:
            # Meta filed this template's first language under another category
            # (Marketing, 22 Oct 2026), and every language of one template must
            # share it: the rest go in under the same.
            result = service.submit(row, theirs)
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


def _category_meta_has(result: dict) -> Optional[str]:
    """The category Meta already has for a template, from its "category doesn't match" refusal."""
    import re
    if result.get("status") == "success":
        return None
    m = re.search(r"already associated with this template, ([A-Z_]+)", result.get("error") or "")
    return m.group(1) if m else None


def submit_all(db: Session, by: str) -> Dict[str, List[dict]]:
    """Every nudge, in every language, to Meta for review; those already there are left as they are."""
    return {key: submit(db, key, by) for key in keys()}
