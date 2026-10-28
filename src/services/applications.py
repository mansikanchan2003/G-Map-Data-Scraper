"""
Applications: the people who started onboarding through the WhatsApp bot.

The bot keeps each person's answers on their conversation (bot_data): the PIN
check, education, franchise background and whether they can invest ₹3–5 lakh,
and the documents they upload are OnboardingDocument rows. An application is
read from those, so it is always as current as the chat itself.

Qualification, as the team defined it:
- PIN qualified: the PIN is within our area.
- Strongly qualified: PIN qualified, at least 12th / Diploma, and Yes to ₹3–5 lakh.
- Not qualified: the PIN is outside our area, education is below 12th, or
  they cannot invest. Someone part-way through is none of these yet.
"""
import re
import time
import uuid
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.models import Business
from src.models.application import ApplicationComment, ApplicationRemoval
from src.models.inbox import OnboardingDocument, WhatsAppConversation, WhatsAppMessage
from src.models.location import Location
from src.models.sbi_branch import SbiBranch
from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient
from src.services import inbox, pincode_coverage
from src.services.geo_validator import haversine_distance
from src.services import onboarding_bot as bot

# The steps of the onboarding flow.
ONBOARDING_STEPS = {
    bot.AWAIT_PIN, bot.AWAIT_EDUCATION, bot.AWAIT_FRANCHISE, bot.NOT_ELIGIBLE,
    bot.AWAIT_INVEST, bot.AWAIT_DOCS, bot.AWAIT_UPLOAD, bot.SUBMITTED,
    bot.NOT_SERVED, bot.NOT_INVESTING,
}
QUALIFICATION = {"12": "12th / Diploma", "grad": "Graduate / Post-Grad", "other": "Below 12th"}
DOC_LABELS = bot.DOCUMENT_LABELS
REQUIRED_KEYS = [d["key"] for d in bot.REQUIRED_DOCUMENTS]


# Asking for personal guidance is a response to a campaign too, and is counted
# as an application (the team's call, 2026-10-15); its stage says which it is.
GUIDANCE_STEPS = {bot.GUIDANCE_QA, bot.AWAIT_WEBINAR, bot.AWAIT_AVAILABILITY, bot.WEBINAR_CONFIRMED, bot.WEBINAR_AVAILABILITY}


def is_application(conv: WhatsAppConversation) -> bool:
    data = conv.bot_data or {}
    if conv.documents_submitted_at or data.get("coverage") or data.get("education"):
        return True
    if conv.bot_step in ONBOARDING_STEPS or conv.bot_step in GUIDANCE_STEPS:
        return True
    if conv.bot_step == bot.CHOOSE_LANG and data.get("next") in (bot.ONBOARD, bot.WEBINAR):
        return True
    # A PIN asked for too many times hands over to a person mid-application.
    return conv.bot_step == bot.HANDOVER and "pin_attempts" in data


def _served(conv: WhatsAppConversation) -> Optional[bool]:
    coverage = (conv.bot_data or {}).get("coverage")
    if not coverage:
        return None
    if "served" in coverage:
        return bool(coverage["served"])
    # Recorded before the PIN result was kept: only a not-served PIN ends there.
    return conv.bot_step != bot.NOT_SERVED


NOT_SBI = "Not qualified for SBI branch code"


def qualify(conv: WhatsAppConversation) -> Dict:
    data = conv.bot_data or {}
    served = _served(conv)
    education = data.get("education")
    can_invest = data.get("can_invest")
    reasons = []
    if served is False:
        reasons.append(NOT_SBI)
    if education == "other":
        reasons.append("Below 12th")
    if can_invest is False:
        reasons.append("Cannot invest ₹3–5 lakh")
    strong = bool(served) and education in ("12", "grad") and can_invest is True
    return {
        "pin_qualified": served is True,
        "strongly_qualified": strong,
        "not_qualified": bool(reasons),
        "not_qualified_reasons": reasons,
        # Outside the branch area alone: still going, for another proposal.
        "other_proposal": served is False and education != "other",
        "verdict": "Strongly qualified" if strong else (NOT_SBI if reasons == [NOT_SBI] else "Not qualified" if reasons
                   else ("PIN qualified" if served else "In progress")),
    }


def _sources(db: Session, phones: List[str]) -> Dict[str, Dict]:
    """The latest campaign that reached each number, and the business it went to."""
    if not phones:
        return {}
    rows = (
        db.query(WhatsAppCampaignRecipient, WhatsAppCampaign, Business)
        .join(WhatsAppCampaign, WhatsAppCampaign.campaign_id == WhatsAppCampaignRecipient.campaign_id)
        .outerjoin(Business, Business.business_id == WhatsAppCampaignRecipient.business_id)
        .filter(WhatsAppCampaignRecipient.phone.in_(phones),
                WhatsAppCampaignRecipient.provider_message_id.isnot(None))
        .order_by(WhatsAppCampaign.created_at)
        .all()
    )
    out = {}
    for r, c, b in rows:  # later campaigns overwrite earlier ones
        sheet = {str(k).strip().lower(): v for k, v in (r.variables or {}).items()} if isinstance(r.variables, dict) else {}
        # The business's Google Maps category, the persona it was found as; for
        # a campaign sent from an uploaded sheet, the sheet's own category column.
        category = (b.category if b else None) or sheet.get("category") or sheet.get("persona")
        out[r.phone] = {"campaign": c.name, "business_name": (b.name if b else None) or r.name,
                        "category": category, "district": b.district if b else None,
                        "state": b.state if b else None}
    return out


# PINs looked up per page load, at most, and for how long: India Post can be
# slow, and whatever is left is filled in on the next load.
GEO_LOOKUPS_PER_LOAD = 15
GEO_SECONDS_PER_LOAD = 20


def _typed_pins(db: Session, convs: List[WhatsAppConversation]) -> Dict[str, str]:
    """
    The PIN each person last typed in the chat, for those the bot holds none for.

    The bot keeps a PIN only once it has placed it on the map; one it could
    not place is asked for again and not kept, though the person did give it.
    """
    missing = [c.phone for c in convs if not ((c.bot_data or {}).get("coverage") or {}).get("pincode")]
    if not missing:
        return {}
    found: Dict[str, str] = {}
    rows = (db.query(WhatsAppMessage.phone, WhatsAppMessage.body)
            .filter(WhatsAppMessage.phone.in_(missing), WhatsAppMessage.direction == "IN",
                    WhatsAppMessage.body.isnot(None))
            .order_by(WhatsAppMessage.created_at.desc()).all())
    for phone, body in rows:
        if phone not in found:
            pin = _standalone_pin(body)
            if pin:
                found[phone] = pin
    return found


# Six digits standing on their own ("363520", "363 520", "pin 363520"), not
# inside a longer code: "1A851679" is a CSP code, not PIN 851679.
_STANDALONE_PIN = re.compile(r"(?<![0-9A-Za-z])([1-9][0-9]{5})(?![0-9A-Za-z])")


def _standalone_pin(text: Optional[str]) -> Optional[str]:
    match = _STANDALONE_PIN.search(re.sub(r"(?<=\d)[\s-](?=\d)", "", text or ""))
    return match.group(1) if match else None


def _pin_coords(db: Session, pin: str) -> Optional[List[float]]:
    """A PIN's coordinates: our own location list first, then the geocoder."""
    loc = db.query(Location).filter(Location.pincode == pin, Location.latitude.isnot(None)).first()
    if loc:
        return [loc.latitude, loc.longitude]
    try:
        lat, lng = pincode_coverage.locate(pin)
    except LookupError:
        return None
    return [lat, lng]


def _fill_geography(db: Session, convs: List[WhatsAppConversation], typed: Dict[str, str]) -> None:
    """
    Gives each application's PIN its state, district, tehsil and coordinates, once.

    The PIN is the one the person gave in the chat. The bot's "place" is the
    nearest of our target PINs, not their own area, so the PIN itself is
    looked up and the answer kept on the conversation (beside the bot's
    check, or under typed_pin for a PIN the bot could not place). The
    coordinates find the nearest SBI branch. Unknown PINs are retried on a
    later load.
    """
    started, looked_up, changed = time.monotonic(), 0, False
    for conv in convs:
        data = conv.bot_data or {}
        coverage = data.get("coverage") or {}
        key, pin = ("coverage", coverage.get("pincode")) if coverage.get("pincode") else ("typed_pin", typed.get(conv.phone))
        held = data.get(key) or {}
        if held.get("pincode") != pin:
            held = {k: v for k, v in held.items() if k not in ("geo", "coords")}
        if not pin or (held.get("geo") and held.get("coords")):
            continue
        if looked_up >= GEO_LOOKUPS_PER_LOAD or time.monotonic() - started > GEO_SECONDS_PER_LOAD:
            break
        looked_up += 1
        found = {}
        geo = held.get("geo") or pincode_coverage.geography(db, pin)
        if geo:
            found["geo"] = geo
        coords = held.get("coords") or _pin_coords(db, pin)
        if coords:
            found["coords"] = coords
        if found:
            conv.bot_data = {**data, key: {**held, "pincode": pin, **found}}
            flag_modified(conv, "bot_data")
            changed = True
    if changed:
        db.commit()


def _branches(db: Session) -> List[Dict]:
    """The SBI branches with their PIN's coordinates, from our location list."""
    coords = {l.pincode: (l.latitude, l.longitude) for l in db.query(Location)
              .filter(Location.pincode.in_(db.query(SbiBranch.pincode)), Location.latitude.isnot(None))}
    return [{"branch_code": b.branch_code, "branch_name": b.branch_name, "ao": b.module,
             "pincode": b.pincode, "coords": coords[b.pincode]}
            for b in db.query(SbiBranch).all() if b.pincode in coords]


# Only the branches the bank gave us are known (Gujarat and Chandigarh so
# far), so the nearest of them can be states away: a Mohali lead was put at
# Viramgam. Past this distance it is not their branch, and none is given.
BRANCH_MAX_KM = 50


def _nearest_branch(branches: List[Dict], coords: Optional[List[float]]) -> Optional[Dict]:
    """The SBI branch nearest a PIN, and how far it is; None if none of ours is within BRANCH_MAX_KM."""
    if not coords or not branches:
        return None
    km, best = min(((haversine_distance(coords[0], coords[1], *b["coords"]), b) for b in branches),
                   key=lambda pair: pair[0])
    if km > BRANCH_MAX_KM:
        return None
    return {k: v for k, v in best.items() if k != "coords"} | {"distance_km": round(km, 1)}


def _iso(value) -> Optional[str]:
    value = inbox.aware(value)
    return value.isoformat() if value else None


def list_applications(db: Session, removed: bool = False) -> Dict:
    """Every application with its qualification, stage, documents and comments, and the totals."""
    removals = {r.phone: r for r in db.query(ApplicationRemoval).all()}
    candidates = [c for c in db.query(WhatsAppConversation)
                  .filter((WhatsAppConversation.bot_step.isnot(None)) | (WhatsAppConversation.documents_submitted_at.isnot(None)))
                  .all() if is_application(c)]
    # Only people an AutoGMap campaign reached, as the bot itself now answers
    # only them: the business number is shared, and before that rule the bot
    # also took in other teams' contacts (an existing CSP asking about his
    # balance showed up as an application).
    ours = inbox.campaign_phones(db, [c.phone for c in candidates])
    convs = [c for c in candidates if c.phone in ours and ((c.phone in removals) == removed)]
    phones = [c.phone for c in convs]
    typed = _typed_pins(db, convs)
    _fill_geography(db, convs, typed)

    docs: Dict[str, List] = {}
    for d in (db.query(OnboardingDocument).filter(OnboardingDocument.phone.in_(phones))
              .order_by(OnboardingDocument.uploaded_at).all() if phones else []):
        docs.setdefault(d.phone, []).append(d)
    comments: Dict[str, List] = {}
    for c in (db.query(ApplicationComment).filter(ApplicationComment.phone.in_(phones))
              .order_by(ApplicationComment.created_at).all() if phones else []):
        comments.setdefault(c.phone, []).append(c)
    sources = _sources(db, phones)
    branches = _branches(db)
    # When the lead came in: their first message or button tap to us.
    first_in = dict(db.query(WhatsAppMessage.phone, func.min(WhatsAppMessage.created_at))
                    .filter(WhatsAppMessage.phone.in_(phones), WhatsAppMessage.direction == "IN")
                    .group_by(WhatsAppMessage.phone).all()) if phones else {}

    items = []
    for conv in convs:
        data = conv.bot_data or {}
        coverage = data.get("coverage") or {}
        # The PIN as given in the chat: the one the bot checked, else the
        # last one they typed.
        typed_pin = typed.get(conv.phone)
        pin_info = coverage if coverage.get("pincode") else (data.get("typed_pin") or {})
        current = pin_info.get("pincode") in (coverage.get("pincode"), typed_pin)
        geo = (pin_info.get("geo") if current else None) or {}
        q = qualify(conv)
        mine = docs.get(conv.phone, [])
        have = {d.doc_type for d in mine}
        items.append({
            "phone": conv.phone,
            "name": conv.profile_name,
            "pincode": coverage.get("pincode") or typed_pin,
            # True when the bot never placed it (it asked again); shown as given.
            "pincode_unchecked": not coverage.get("pincode") and bool(typed_pin),
            "state": geo.get("state"),
            "district": geo.get("district"),
            "tehsil": geo.get("tehsil"),
            # The nearest of our target PINs and how far it is, from the bot's check.
            "place": coverage.get("place"),
            "distance_km": coverage.get("distance_km"),
            # The SBI branch nearest their PIN: its code, name, AO and how far.
            "sbi_branch": _nearest_branch(branches, pin_info.get("coords") if current else None),
            "category": (sources.get(conv.phone) or {}).get("category"),
            "qualification": QUALIFICATION.get(data.get("education")),
            "franchise_background": data.get("franchise"),
            "can_invest": data.get("can_invest"),
            "language": data.get("lang"),
            "stage": bot.STEP_LABELS.get(conv.bot_step, conv.bot_step or "—"),
            "bot_step": conv.bot_step,
            **q,
            "documents": [{"document_id": d.document_id, "type": d.doc_type,
                           "label": DOC_LABELS.get(d.doc_type, d.doc_type), "name": d.original_name,
                           "drive_url": d.drive_url, "uploaded_at": _iso(d.uploaded_at)} for d in mine],
            "documents_count": len(have),
            "documents_total": len(bot.DOCUMENTS),
            "required_documents_done": all(k in have for k in REQUIRED_KEYS),
            "drive_folder_url": conv.drive_folder_url,
            "submitted": conv.documents_submitted_at is not None,
            "submitted_at": _iso(conv.documents_submitted_at),
            "started_at": _iso(conv.created_at),
            "lead_at": _iso(first_in.get(conv.phone) or conv.created_at),
            "last_message_at": _iso(conv.last_message_at),
            "source": sources.get(conv.phone),
            "comments": [{"comment_id": c.comment_id, "body": c.body, "author": c.author,
                          "created_at": _iso(c.created_at)} for c in comments.get(conv.phone, [])],
            "removed": conv.phone in removals,
            "removed_by": removals[conv.phone].removed_by if conv.phone in removals else None,
        })
    items.sort(key=lambda a: a["last_message_at"] or "", reverse=True)

    stats = {
        "total": len(items),
        "pin_qualified": sum(a["pin_qualified"] for a in items),
        "strongly_qualified": sum(a["strongly_qualified"] for a in items),
        "not_qualified": sum(a["not_qualified"] for a in items),
        "submitted": sum(a["submitted"] for a in items),
        "removed": len(removals) if not removed else len(items),
    }
    return {"stats": stats, "items": items}


def _conversation(db: Session, phone: str) -> WhatsAppConversation:
    conv = db.get(WhatsAppConversation, phone)
    if conv is None or not is_application(conv):
        raise LookupError("No such application")
    return conv


def add_comment(db: Session, phone: str, body: str, author: str) -> ApplicationComment:
    _conversation(db, phone)
    # Stamped here to the microsecond, so comments added in quick succession
    # keep their order.
    comment = ApplicationComment(comment_id=uuid.uuid4().hex, phone=phone, body=body.strip(), author=author,
                                 created_at=inbox.now())
    db.add(comment)
    db.commit()
    return comment


def delete_comment(db: Session, comment_id: str) -> None:
    comment = db.get(ApplicationComment, comment_id)
    if comment is None:
        raise LookupError("No such comment")
    db.delete(comment)
    db.commit()


def remove(db: Session, phone: str, by: str) -> None:
    """Takes the application off the tab; the chat and documents stay."""
    _conversation(db, phone)
    if db.get(ApplicationRemoval, phone) is None:
        db.add(ApplicationRemoval(phone=phone, removed_by=by))
        db.commit()


def restore(db: Session, phone: str) -> None:
    removal = db.get(ApplicationRemoval, phone)
    if removal is not None:
        db.delete(removal)
        db.commit()
