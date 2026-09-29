from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import uuid
import logging
from datetime import datetime, timedelta, timezone
import os
import shutil
from fastapi.responses import FileResponse
from src.database import get_db
from src.models.whatsapp import (
    WhatsAppAccount, WhatsAppTemplate, WhatsAppCampaign,
    WhatsAppCampaignRecipient, WhatsAppCampaignLog, WhatsAppLinkClick,
    WhatsAppButtonClick, WhatsAppReply
)
from src.schemas.whatsapp import (
    WhatsAppAccountCreate, WhatsAppAccountUpdate, WhatsAppAccountResponse,
    WhatsAppTemplateCreate, WhatsAppTemplateUpdate, WhatsAppTemplateResponse,
    WhatsAppContactValidateRequest, WhatsAppContactValidateResponse,
    WhatsAppCampaignPreviewRequest, WhatsAppCampaignCreate, WhatsAppCampaignResponse,
    WhatsAppCampaignRecipientResponse, WhatsAppCampaignLogResponse,
    WhatsAppCampaignLogsResponse, MetaTemplateListResponse,
    WhatsAppTemplateSubmitRequest, WhatsAppTemplateSubmitResponse,
    WhatsAppTemplateSyncResponse
)
from src.models.user import User
from src.routers.auth import current_user
from src.services import auth_service, notifier, pricing
from src.services.whatsapp_normalizer import WhatsAppNormalizer
from src.services.meta_whatsapp_service import MetaWhatsAppService
# We will import whatsapp_service here later for campaign execution.
# from src.services.whatsapp_service import execute_campaign

logger = logging.getLogger("gmap_scraper.whatsapp")

router = APIRouter(prefix="/api/v1/whatsapp", tags=["WhatsApp Campaigns"])

# --- Accounts ---

@router.get("/accounts", response_model=List[WhatsAppAccountResponse])
def list_accounts(db: Session = Depends(get_db)):
    return db.query(WhatsAppAccount).all()

@router.post("/accounts", response_model=WhatsAppAccountResponse)
def create_account(account: WhatsAppAccountCreate, db: Session = Depends(get_db)):
    db_acc = WhatsAppAccount(
        account_id=uuid.uuid4().hex,
        display_name=account.display_name,
        phone_number=account.phone_number,
        phone_number_id=account.phone_number_id,
        waba_id=account.waba_id,
        status="Configuration Pending"
    )
    db.add(db_acc)
    db.commit()
    db.refresh(db_acc)
    return db_acc

@router.patch("/accounts/{account_id}", response_model=WhatsAppAccountResponse)
def update_account(account_id: str, updates: WhatsAppAccountUpdate, db: Session = Depends(get_db)):
    db_acc = db.query(WhatsAppAccount).filter(WhatsAppAccount.account_id == account_id).first()
    if not db_acc:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = updates.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_acc, key, value)

    db.commit()
    db.refresh(db_acc)
    return db_acc

@router.post("/accounts/connect", response_model=WhatsAppAccountResponse)
def connect_account(db: Session = Depends(get_db)):
    """
    Verifies connection to Meta using environment variables.
    If successful, creates or updates the WhatsAppAccount in DB.
    """
    service = MetaWhatsAppService()

    result = service.verify_connection()

    if result["status"] != "success":
        error_msg = result.get("error", "Meta WhatsApp authentication failed")
        raise HTTPException(status_code=400, detail=error_msg)

    phone_number_id = service.phone_number_id
    display_phone_number = result.get("display_phone_number")
    verified_name = result.get("verified_name")

    # Check if we have an account for this phone_number_id or phone_number
    db_acc = db.query(WhatsAppAccount).filter(
        (WhatsAppAccount.phone_number_id == phone_number_id) |
        (WhatsAppAccount.phone_number == display_phone_number)
    ).first()

    if db_acc:
        db_acc.status = "Connected"
        db_acc.phone_number_id = phone_number_id
        if verified_name:
            db_acc.display_name = verified_name
        if display_phone_number:
            db_acc.phone_number = display_phone_number
        db.commit()
        db.refresh(db_acc)
        return db_acc
    else:
        new_acc = WhatsAppAccount(
            account_id=uuid.uuid4().hex,
            display_name=verified_name,
            phone_number=display_phone_number or "Unknown",
            phone_number_id=phone_number_id,
            status="Connected"
        )
        db.add(new_acc)
        db.commit()
        db.refresh(new_acc)
        return new_acc

# --- Media Upload ---

@router.post("/media/upload")
async def upload_media(file: UploadFile = File(...), media_type: str = Form(...)):
    import os, uuid, shutil
    from fastapi import HTTPException

    if media_type not in ["image", "video"]:
        raise HTTPException(status_code=400, detail="Invalid media_type. Must be 'image' or 'video'.")

    # Meta enforces a different ceiling per media type, and rejects anything
    # above it at send time with a bare "(#100) Invalid parameter". Applying the
    # same limits here means an oversized file is refused while the user is
    # still looking at the upload dialog, instead of failing a whole campaign.
    META_MEDIA_LIMITS_MB = {"image": 5.0, "video": 16.0}
    max_size_mb = META_MEDIA_LIMITS_MB[media_type]
    override = os.environ.get("WHATSAPP_MEDIA_MAX_SIZE_MB")
    if override:
        # An override may only tighten the limit; Meta's ceiling is not ours to raise.
        max_size_mb = min(max_size_mb, float(override))
    max_size_bytes = int(max_size_mb * 1024 * 1024)

    # Check file size by seeking
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File is {file_size / 1024 / 1024:.1f}MB. WhatsApp allows at most "
                f"{max_size_mb:g}MB for a {media_type} header - please compress it and try again."
            ),
        )

    # Validate extensions
    ext = os.path.splitext(file.filename)[1].lower()
    if media_type == "image" and ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="Unsupported image format. Allowed: jpg, jpeg, png, webp.")
    elif media_type == "video" and ext not in [".mp4"]:
        raise HTTPException(status_code=400, detail="Unsupported video format. Allowed: mp4.")

    media_id = f"{uuid.uuid4().hex}{ext}"
    media_dir = os.path.join("data", "whatsapp_media")
    os.makedirs(media_dir, exist_ok=True)

    file_path = os.path.join(media_dir, media_id)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "status": "success",
        "media_id": media_id,
        "media_type": media_type,
        "filename": file.filename,
        "mime_type": file.content_type,
        "size_bytes": file_size
    }

@router.get("/media/{media_id}")
def get_media(media_id: str):
    import os
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    # Basic path traversal protection
    media_id = os.path.basename(media_id)
    file_path = os.path.join("data", "whatsapp_media", media_id)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Media not found")

    return FileResponse(file_path)

# --- Templates ---

@router.get("/templates", response_model=List[WhatsAppTemplateResponse])
def list_templates(db: Session = Depends(get_db)):
    return db.query(WhatsAppTemplate).order_by(WhatsAppTemplate.created_at.desc()).all()

@router.get("/templates/meta", response_model=MetaTemplateListResponse)
def list_meta_templates():
    """
    Lists the templates registered in the Meta WhatsApp Business Account.

    A campaign can only send a template that is APPROVED here. Local template
    rows are drafts for composing/previewing and are not known to Meta until
    they are submitted and approved.
    """
    service = MetaWhatsAppService()
    result = service.list_message_templates()
    if result["status"] != "success":
        return MetaTemplateListResponse(status="failed", templates=[], error=result.get("error"))
    return MetaTemplateListResponse(status="success", templates=result["templates"])


@router.post("/templates", response_model=WhatsAppTemplateResponse)
def create_template(template: WhatsAppTemplateCreate, db: Session = Depends(get_db)):
    db_tmpl = WhatsAppTemplate(
        template_id=uuid.uuid4().hex,
        name=template.name,
        meta_template_name=template.meta_template_name,
        language_code=template.language_code or "en_US",
        category=(template.category or "MARKETING").upper(),
        header_type=template.header_type,
        header_content=template.header_content,
        body=template.body,
        footer=template.footer,
        buttons=template.buttons,
        status=template.status or "Draft"
    )
    db.add(db_tmpl)
    db.commit()
    db.refresh(db_tmpl)

    if template.auto_submit:
        # Submission is best-effort: a template that Meta rejects outright
        # (bad name, missing media, policy) stays a local draft that can be
        # edited and resubmitted, rather than failing the whole creation.
        from src.services.whatsapp_service import WhatsAppTemplateSubmissionService

        result = WhatsAppTemplateSubmissionService(db).submit(
            db_tmpl, category=template.category or "MARKETING"
        )
        db.refresh(db_tmpl)
        if result["status"] != "success":
            response = WhatsAppTemplateResponse.model_validate(db_tmpl)
            response.submission_error = result.get("error")
            return response

    return db_tmpl

@router.get("/templates/{template_id}", response_model=WhatsAppTemplateResponse)
def get_template(template_id: str, db: Session = Depends(get_db)):
    db_tmpl = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id == template_id).first()
    if not db_tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return db_tmpl

@router.patch("/templates/{template_id}", response_model=WhatsAppTemplateResponse)
def update_template(template_id: str, updates: WhatsAppTemplateUpdate, db: Session = Depends(get_db)):
    db_tmpl = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id == template_id).first()
    if not db_tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    update_data = updates.dict(exclude_unset=True)

    # Kept so a change Meta refuses can be undone. What we send is built from
    # this row, so a local copy that has drifted from the approved template
    # makes every later send fail — a button retyped here but still a Call at
    # Meta produced "#132018 Button at index 1 ... does not support
    # parameters" on every recipient.
    CONTENT_FIELDS = ("body", "footer", "header_type", "header_content", "buttons")
    previous = {k: getattr(db_tmpl, k) for k in CONTENT_FIELDS}

    for key, value in update_data.items():
        setattr(db_tmpl, key, value)

    db.commit()
    db.refresh(db_tmpl)

    # A template's text lives with Meta: a send supplies only the name and
    # parameters, and Meta renders the message from its own copy. Editing
    # locally therefore changes the preview but NOT what recipients receive,
    # so the edit is pushed to Meta rather than left to diverge silently.
    from src.services.whatsapp_service import WhatsAppTemplateEditService

    content_changed = any(k in update_data for k in CONTENT_FIELDS)
    response = WhatsAppTemplateResponse.model_validate(db_tmpl)

    if content_changed and db_tmpl.meta_template_name:
        result = WhatsAppTemplateEditService(db).push(db_tmpl)
        db.refresh(db_tmpl)
        response = WhatsAppTemplateResponse.model_validate(db_tmpl)
        if result["status"] != "success":
            # Rolled back rather than left to diverge: Meta renders from its
            # own copy, so keeping the rejected version here would change
            # nothing for recipients while breaking every send.
            for key, value in previous.items():
                setattr(db_tmpl, key, value)
            db.commit()
            db.refresh(db_tmpl)
            response = WhatsAppTemplateResponse.model_validate(db_tmpl)
            response.submission_error = (
                f"Meta did not accept the change: {result['error']} "
                f"The template has been left as Meta approved it — an approved "
                f"template's buttons and header cannot be changed, so a "
                f"different layout needs a new template."
            )
    elif content_changed and not db_tmpl.meta_template_name:
        response.submission_error = (
            "Saved locally. This template has never been submitted to Meta, "
            "so it cannot be sent until you submit it for review."
        )

    return response

def _meta_status_to_local(meta_status: str) -> str:
    """
    Meta's review states are stored verbatim (APPROVED / PENDING / REJECTED /
    PAUSED / DISABLED) rather than remapped, so the dashboard shows the same
    words the Meta dashboard does.
    """
    return (meta_status or "PENDING").upper()


@router.post("/templates/sync-status", response_model=WhatsAppTemplateSyncResponse)
def sync_template_statuses(db: Session = Depends(get_db)):
    """
    Refreshes every submitted local template from the Meta WABA in one call.

    Templates that were never submitted keep their Draft status: Meta does not
    know about them, so there is no review state to report.
    """
    listing = MetaWhatsAppService().list_message_templates()
    if listing["status"] != "success":
        return WhatsAppTemplateSyncResponse(
            status="failed", checked=0, updated=0, error=listing.get("error")
        )

    # (name, language) is how Meta identifies a template.
    remote = {
        (t.get("name"), t.get("language")): t
        for t in listing["templates"]
    }

    templates = db.query(WhatsAppTemplate).all()
    checked = 0
    updated = 0

    for tmpl in templates:
        if not tmpl.meta_template_name:
            continue
        checked += 1
        entry = remote.get((tmpl.meta_template_name, tmpl.language_code or "en_US"))
        if entry is None:
            # Submitted earlier but absent now: it was deleted on Meta's side.
            new_status = "Draft"
            new_category = tmpl.category
        else:
            new_status = _meta_status_to_local(entry.get("status"))
            # Meta may reclassify a template during review, so its category is
            # taken from Meta rather than from what was requested on submit.
            new_category = entry.get("category") or tmpl.category

        if tmpl.status != new_status or tmpl.category != new_category:
            tmpl.status = new_status
            tmpl.category = new_category
            updated += 1

    db.commit()
    return WhatsAppTemplateSyncResponse(status="success", checked=checked, updated=updated)


@router.post("/templates/{template_id}/submit", response_model=WhatsAppTemplateSubmitResponse)
def submit_template(template_id: str, req: WhatsAppTemplateSubmitRequest = None, db: Session = Depends(get_db)):
    """
    Submits a local template to the Meta WABA for approval.

    Until a template is approved by Meta it cannot be sent -- Meta resolves a
    send by the registered (name, language) pair, which is what produces the
    #132001 rejection for locally-created drafts.
    """
    from src.services.whatsapp_service import WhatsAppTemplateSubmissionService

    db_tmpl = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id == template_id).first()
    if not db_tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    category = (req.category if req else None) or "MARKETING"
    service = WhatsAppTemplateSubmissionService(db)
    result = service.submit(db_tmpl, category=category)

    if result["status"] != "success":
        return WhatsAppTemplateSubmitResponse(
            status="failed", error=result.get("error"), error_code=result.get("error_code")
        )
    return WhatsAppTemplateSubmitResponse(**{"status": "success", **{
        k: v for k, v in result.items() if k in
        ("meta_template_name", "language_code", "meta_status")}})


@router.post("/templates/{template_id}/refresh-status", response_model=WhatsAppTemplateResponse)
def refresh_template_status(template_id: str, db: Session = Depends(get_db)):
    """Pulls the current Meta review status for an already-submitted template."""
    db_tmpl = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id == template_id).first()
    if not db_tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    if not db_tmpl.meta_template_name:
        raise HTTPException(status_code=400, detail="Template has not been submitted to Meta yet")

    listing = MetaWhatsAppService().list_message_templates()
    if listing["status"] != "success":
        raise HTTPException(status_code=502, detail=listing.get("error", "Could not reach Meta"))

    for t in listing["templates"]:
        if t.get("name") == db_tmpl.meta_template_name and t.get("language") == db_tmpl.language_code:
            db_tmpl.status = _meta_status_to_local(t.get("status"))
            db.commit()
            db.refresh(db_tmpl)
            break

    return db_tmpl


@router.delete("/templates/{template_id}")
def delete_template(template_id: str, db: Session = Depends(get_db)):
    """
    Removes the local template.

    Past campaigns keep their history; their link to this template is cleared,
    and the campaign detail view reports the template as no longer available.
    The copy registered with Meta is left untouched, so the name stays in use
    there and sends from other systems are unaffected.
    """
    db_tmpl = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id == template_id).first()
    if not db_tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    campaigns_using = db.query(WhatsAppCampaign).filter(
        WhatsAppCampaign.template_id == template_id
    ).count()

    name = db_tmpl.name
    meta_name = db_tmpl.meta_template_name

    try:
        db.delete(db_tmpl)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception(f"whatsapp_template event=TEMPLATE_DELETE_FAILED template_id={template_id}")
        raise HTTPException(
            status_code=409,
            detail=f"Could not delete '{name}': {exc.__class__.__name__}. It may still be in use.",
        )

    logger.info(
        f"whatsapp_template event=TEMPLATE_DELETED template_id={template_id} "
        f"name={name} campaigns_unlinked={campaigns_using}"
    )
    return {
        "status": "success",
        "campaigns_unlinked": campaigns_using,
        "meta_template_kept": meta_name,
    }

# --- Contacts & Validation ---

@router.post("/contacts/validate", response_model=WhatsAppContactValidateResponse)
def validate_contacts(req: WhatsAppContactValidateRequest):
    valid_contacts = []
    invalid_contacts = []
    seen_phones = set()

    empty_count = 0
    landline_count = 0
    duplicate_count = 0
    invalid_count = 0

    for c in req.contacts:
        raw_phone = c.get("phone")
        name = c.get("name")
        business_id = c.get("business_id")

        canonical, error = WhatsAppNormalizer.normalize_phone(raw_phone)

        if error:
            if "Empty" in error:
                empty_count += 1
            elif "Landline" in error:
                landline_count += 1
            else:
                invalid_count += 1

            invalid_contacts.append({
                "raw_phone": raw_phone,
                "name": name,
                "error_reason": error
            })
        else:
            if canonical in seen_phones:
                duplicate_count += 1
            else:
                seen_phones.add(canonical)
                valid_contacts.append({
                    "phone": canonical,
                    "name": name,
                    "business_id": business_id
                })

    return WhatsAppContactValidateResponse(
        total_records=len(req.contacts),
        valid_mobile_numbers=len(valid_contacts) + duplicate_count,
        invalid_numbers=invalid_count,
        empty_phone_numbers=empty_count,
        landlines=landline_count,
        duplicates_removed=duplicate_count,
        final_sendable_contacts=len(valid_contacts),
        valid_contacts=valid_contacts,
        invalid_contacts=invalid_contacts
    )

# --- Campaigns ---

from src.services.whatsapp_service import WhatsAppCampaignService

@router.post("/campaigns", response_model=WhatsAppCampaignResponse)
def create_campaign(req: WhatsAppCampaignCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Verify account
    acc = db.query(WhatsAppAccount).filter(WhatsAppAccount.account_id == req.account_id).first()
    if not acc:
        raise HTTPException(status_code=400, detail="Invalid WhatsApp Account")

    # Verify template
    tmpl = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id == req.template_id).first()
    if not tmpl:
        raise HTTPException(status_code=400, detail="Invalid Template")

    # Validation passes, create Campaign record
    campaign_service = WhatsAppCampaignService(db)
    campaign = campaign_service.create_campaign_and_recipients(
        name=req.name,
        template_id=req.template_id,
        account_id=req.account_id,
        data_source_type=req.data_source_type,
        contacts=req.contacts
    )

    # Launch execution in background
    background_tasks.add_task(campaign_service.execute_campaign, campaign.campaign_id)

    return campaign

def _visit_counts(db: Session, campaign_ids: List[str]) -> dict:
    """
    Real click counts per campaign, derived only from recorded clicks.

    A recipient who opened the link five times counts as one unique visit and
    four repeated ones, so the two columns never double-count the same person.
    """
    if not campaign_ids:
        return {}

    from sqlalchemy import func as sa_func

    rows = (
        db.query(
            WhatsAppLinkClick.campaign_id,
            WhatsAppLinkClick.recipient_id,
            sa_func.count(WhatsAppLinkClick.click_id).label("clicks"),
        )
        .filter(WhatsAppLinkClick.campaign_id.in_(campaign_ids))
        .group_by(WhatsAppLinkClick.campaign_id, WhatsAppLinkClick.recipient_id)
        .all()
    )

    counts = {cid: {"unique": 0, "repeated": 0, "total": 0} for cid in campaign_ids}
    for campaign_id, _recipient_id, clicks in rows:
        entry = counts[campaign_id]
        entry["unique"] += 1
        entry["repeated"] += max(clicks - 1, 0)
        entry["total"] += clicks
    return counts


def _delivery_counts(db: Session, campaign_ids: List[str]) -> dict:
    """
    Delivery and quick-reply totals per campaign, from recorded events only.

    Delivered and read accumulate rather than partition: every read message was
    also delivered, so read is a subset of delivered, not a separate bucket.

    "Undelivered" counts only messages Meta actually reported a failure for.
    A sent message with no webhook yet is unknown, not undelivered — calling it
    undelivered would report a failure that never happened.
    """
    empty = {
        "delivered": 0, "read": 0, "undelivered": 0,
        "button_clicks": 0, "button_clickers": 0, "reported": 0,
        "with_report": 0,
    }
    if not campaign_ids:
        return {}

    from sqlalchemy import func as sa_func

    counts = {cid: dict(empty) for cid in campaign_ids}

    rows = (
        db.query(
            WhatsAppCampaignRecipient.campaign_id,
            sa_func.count(WhatsAppCampaignRecipient.delivered_at).label("delivered"),
            sa_func.count(WhatsAppCampaignRecipient.read_at).label("read"),
            sa_func.count(WhatsAppCampaignRecipient.failed_at).label("failed"),
            # Recipients Meta has said anything terminal about. Unlike
            # `reported` below this counts each recipient once, which is what
            # pricing needs: read is a subset of delivered, so adding the two
            # would bill the same message twice.
            sa_func.count(sa_func.coalesce(
                WhatsAppCampaignRecipient.delivered_at,
                WhatsAppCampaignRecipient.failed_at,
            )).label("with_report"),
        )
        .filter(WhatsAppCampaignRecipient.campaign_id.in_(campaign_ids))
        .group_by(WhatsAppCampaignRecipient.campaign_id)
        .all()
    )
    for campaign_id, delivered, read, failed, with_report in rows:
        entry = counts[campaign_id]
        entry["delivered"] = delivered
        entry["read"] = read
        entry["undelivered"] = failed
        entry["with_report"] = with_report
        # Anything Meta has told us about counts as delivery data existing.
        entry["reported"] = delivered + read + failed

    clicks = (
        db.query(
            WhatsAppButtonClick.campaign_id,
            sa_func.count(WhatsAppButtonClick.click_id).label("taps"),
            sa_func.count(sa_func.distinct(WhatsAppButtonClick.recipient_id)).label("people"),
        )
        .filter(WhatsAppButtonClick.campaign_id.in_(campaign_ids))
        .group_by(WhatsAppButtonClick.campaign_id)
        .all()
    )
    for campaign_id, taps, people in clicks:
        counts[campaign_id]["button_clicks"] = taps
        counts[campaign_id]["button_clickers"] = people

    return counts


def _with_visits(db: Session, campaigns: list) -> List[WhatsAppCampaignResponse]:
    ids = [c.campaign_id for c in campaigns]
    counts = _visit_counts(db, ids)
    delivery = _delivery_counts(db, ids)

    # The rate follows the template's category, so it is read once per page
    # rather than per campaign.
    template_ids = [c.template_id for c in campaigns if c.template_id]
    categories = {}
    if template_ids:
        categories = {
            t.template_id: (t.category or pricing.DEFAULT_CATEGORY).upper()
            for t in db.query(WhatsAppTemplate).filter(
                WhatsAppTemplate.template_id.in_(template_ids)
            ).all()
        }

    out = []
    for c in campaigns:
        item = WhatsAppCampaignResponse.model_validate(c)
        stat = counts.get(c.campaign_id, {})
        item.unique_visits = stat.get("unique", 0)
        item.repeated_visits = stat.get("repeated", 0)
        item.total_clicks = stat.get("total", 0)

        d = delivery.get(c.campaign_id, {})
        item.delivered_count = d.get("delivered", 0)
        item.read_count = d.get("read", 0)
        item.undelivered_count = d.get("undelivered", 0)
        item.button_click_count = d.get("button_clicks", 0)
        item.button_clickers = d.get("button_clickers", 0)
        item.has_delivery_data = d.get("reported", 0) > 0

        # Meta bills on delivery, and the webhook went live part-way through
        # this account's history. Counting only confirmed deliveries priced a
        # 621-recipient campaign at three messages; counting every send
        # ignores the failures Meta did report. So each recipient is counted
        # the way we know it: confirmed deliveries as delivered, and sends we
        # never heard back about as delivered too, which is the ceiling.
        category = categories.get(c.template_id) or pricing.DEFAULT_CATEGORY
        sent = c.successful_count or 0
        unreported = max(0, sent - d.get("with_report", 0))
        billable = item.delivered_count + unreported
        basis = "delivered" if unreported == 0 else "sent"
        cost = pricing.estimate(category, billable)
        item.currency = cost["currency"]
        item.billing_category = category
        item.rate_per_message = cost["rate"]
        item.billable_messages = cost["billable_messages"]
        item.cost_net = cost["net"]
        item.cost_gst = cost["gst"]
        item.cost_total = cost["total"]
        item.cost_basis = basis

        out.append(item)
    return out


@router.get("/campaigns", response_model=List[WhatsAppCampaignResponse])
def list_campaigns(db: Session = Depends(get_db)):
    campaigns = db.query(WhatsAppCampaign).order_by(WhatsAppCampaign.created_at.desc()).all()
    return _with_visits(db, campaigns)

@router.get("/campaigns/{campaign_id}", response_model=WhatsAppCampaignResponse)
def get_campaign(campaign_id: str, db: Session = Depends(get_db)):
    camp = db.query(WhatsAppCampaign).filter(WhatsAppCampaign.campaign_id == campaign_id).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return _with_visits(db, [camp])[0]

class PaginatedRecipients(BaseModel):
    items: List[WhatsAppCampaignRecipientResponse]
    total: int
    page: int
    page_size: int

@router.get("/campaigns/{campaign_id}/recipients", response_model=PaginatedRecipients)
def get_campaign_recipients(
    campaign_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    from sqlalchemy import func as sa_func

    query = db.query(WhatsAppCampaignRecipient).filter(WhatsAppCampaignRecipient.campaign_id == campaign_id)
    total = query.count()
    items = query.order_by(WhatsAppCampaignRecipient.created_at.asc()).offset((page - 1) * page_size).limit(page_size).all()

    # Clicks are counted for this page's recipients only, rather than per row,
    # so a 500-row page stays two queries instead of a thousand.
    ids = [i.recipient_id for i in items]
    taps, links = {}, {}

    # Categories for this page, in two queries rather than one per row.
    #
    # business_id is the precise link, but every recipient created before it
    # was plumbed through carries none — 2,204 of them — so the phone number
    # is used as a fallback. That is what the audience was selected by in the
    # first place, and both sides store it in the same canonical form.
    from src.models import Business

    categories = {}
    phone_categories = {}

    business_ids = [i.business_id for i in items if i.business_id]
    if business_ids:
        categories = dict(
            db.query(Business.business_id, Business.category)
            .filter(Business.business_id.in_(business_ids))
            .all()
        )

    unlinked_phones = [i.phone for i in items if not i.business_id and i.phone]
    if unlinked_phones:
        # A number can belong to more than one listing; the first is taken
        # rather than pretending the choice is meaningful.
        for phone, category in (
            db.query(Business.phone, Business.category)
            .filter(Business.phone.in_(unlinked_phones))
            .all()
        ):
            phone_categories.setdefault(phone, category)

    if ids:
        for rid, count, last_text in (
            db.query(
                WhatsAppButtonClick.recipient_id,
                sa_func.count(WhatsAppButtonClick.click_id),
                sa_func.max(WhatsAppButtonClick.button_text),
            )
            .filter(WhatsAppButtonClick.recipient_id.in_(ids))
            .group_by(WhatsAppButtonClick.recipient_id)
            .all()
        ):
            taps[rid] = (count, last_text)

        for rid, count in (
            db.query(
                WhatsAppLinkClick.recipient_id,
                sa_func.count(WhatsAppLinkClick.click_id),
            )
            .filter(WhatsAppLinkClick.recipient_id.in_(ids))
            .group_by(WhatsAppLinkClick.recipient_id)
            .all()
        ):
            links[rid] = count

    out = []
    for i in items:
        item = WhatsAppCampaignRecipientResponse.model_validate(i)
        tap_count, last_text = taps.get(i.recipient_id, (0, None))
        item.button_clicks = tap_count
        item.last_button_text = last_text
        item.link_clicks = links.get(i.recipient_id, 0)
        item.category = (categories.get(i.business_id) if i.business_id
                         else phone_categories.get(i.phone))
        out.append(item)

    return PaginatedRecipients(
        items=out,
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/campaigns/{campaign_id}/logs", response_model=WhatsAppCampaignLogsResponse)
def get_campaign_logs(campaign_id: str, db: Session = Depends(get_db)):
    """
    Returns the persisted execution log for a campaign, so a failure can be
    diagnosed from the UI instead of only from container logs.
    """
    camp = db.query(WhatsAppCampaign).filter(WhatsAppCampaign.campaign_id == campaign_id).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")

    logs = db.query(WhatsAppCampaignLog)\
        .filter(WhatsAppCampaignLog.campaign_id == campaign_id)\
        .order_by(WhatsAppCampaignLog.created_at.asc())\
        .all()

    duration = None
    if camp.started_at and camp.completed_at:
        duration = (camp.completed_at - camp.started_at).total_seconds()

    return WhatsAppCampaignLogsResponse(
        campaign_id=camp.campaign_id,
        status=camp.status,
        started_at=camp.started_at,
        completed_at=camp.completed_at,
        duration_seconds=duration,
        total_contacts=camp.total_contacts,
        successful_count=camp.successful_count,
        failed_count=camp.failed_count,
        skipped_count=camp.skipped_count,
        items=[WhatsAppCampaignLogResponse.model_validate(l) for l in logs],
    )


@router.post("/campaigns/{campaign_id}/resume", response_model=WhatsAppCampaignResponse)
def resume_campaign(campaign_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Restarts a stopped campaign for the recipients it never reached.

    Only recipients still in PENDING (or left stuck in PROCESSING by a crash)
    are picked up, so nobody who already received the message is contacted
    twice.
    """
    camp = db.query(WhatsAppCampaign).filter(WhatsAppCampaign.campaign_id == campaign_id).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if camp.status == "RUNNING":
        raise HTTPException(status_code=400, detail="Campaign is already running")

    # A crash can leave recipients claimed but unsent; return them to the queue.
    requeued = db.query(WhatsAppCampaignRecipient).filter(
        WhatsAppCampaignRecipient.campaign_id == campaign_id,
        WhatsAppCampaignRecipient.status == "PROCESSING",
    ).update({"status": "PENDING"}, synchronize_session=False)

    remaining = db.query(WhatsAppCampaignRecipient).filter(
        WhatsAppCampaignRecipient.campaign_id == campaign_id,
        WhatsAppCampaignRecipient.status == "PENDING",
    ).count()

    if remaining == 0:
        db.commit()
        raise HTTPException(status_code=400, detail="Nothing left to send for this campaign")

    camp.status = "PENDING"
    camp.pending_count = remaining
    camp.completed_at = None
    db.commit()
    db.refresh(camp)

    import logging
    logging.getLogger("gmap_scraper.whatsapp_campaign").info(
        f"whatsapp_campaign campaign_id={campaign_id} event=CAMPAIGN_RESUMED "
        f"remaining={remaining} requeued_from_processing={requeued}"
    )

    campaign_service = WhatsAppCampaignService(db)
    background_tasks.add_task(campaign_service.execute_campaign, campaign_id)
    return camp


@router.post("/campaigns/{campaign_id}/cancel")
def cancel_campaign(campaign_id: str, db: Session = Depends(get_db)):
    camp = db.query(WhatsAppCampaign).filter(WhatsAppCampaign.campaign_id == campaign_id).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if camp.status in ["COMPLETED", "FAILED", "CANCELLED"]:
        raise HTTPException(status_code=400, detail="Campaign is already finished")

    camp.status = "CANCELLED"
    # The background worker checks campaign status periodically and will stop
    db.commit()
    return {"status": "success", "message": "Campaign cancellation requested."}

# --- Webhook event handling -------------------------------------------------

def _parse_ts(raw) -> datetime:
    """Meta stamps events with unix seconds; fall back to arrival time."""
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _apply_status_event(db: Session, status: dict) -> None:
    """
    Record one delivery status against the recipient it belongs to.

    Each stage is written to its own timestamp and never cleared. Meta delivers
    these out of order and repeats them, so an event only fills a blank: a
    redelivered "delivered" after "read" must not move the delivered time, and
    must not drag the status backwards either.
    """
    msg_id = status.get("id")
    stage = (status.get("status") or "").upper()
    if not msg_id or not stage:
        return

    recipient = db.query(WhatsAppCampaignRecipient).filter(
        WhatsAppCampaignRecipient.provider_message_id == msg_id
    ).first()
    if not recipient:
        return

    at = _parse_ts(status.get("timestamp"))
    # How far along the lifecycle each stage sits, so a late-arriving earlier
    # event cannot overwrite a later one.
    RANK = {"PENDING": 0, "SENDING": 1, "SENT": 2, "DELIVERED": 3, "READ": 4}

    if stage == "FAILED":
        if recipient.failed_at is None:
            recipient.failed_at = at
        errors = status.get("errors") or []
        if errors:
            err = errors[0]
            recipient.failure_code = str(err.get("code")) if err.get("code") is not None else None
            details = (err.get("error_data") or {}).get("details") or ""
            recipient.reason = f"[{err.get('code')}] {err.get('title', '')} {details}".strip()
        elif not recipient.reason:
            recipient.reason = "Delivery failed (reported by Meta)"
        # A failure is terminal whatever arrived before it.
        recipient.status = "FAILED"
    elif stage in ("SENT", "DELIVERED", "READ"):
        field = {"SENT": "sent_at", "DELIVERED": "delivered_at", "READ": "read_at"}[stage]
        if getattr(recipient, field) is None:
            setattr(recipient, field, at)
        # A read message was delivered even if that event never arrived, and
        # leaving the earlier stamp blank would undercount deliveries.
        if stage == "READ" and recipient.delivered_at is None:
            recipient.delivered_at = at
        if recipient.status != "FAILED" and RANK.get(stage, 0) > RANK.get(recipient.status, 0):
            recipient.status = stage
    else:
        return

    db.add(WhatsAppCampaignLog(
        log_id=uuid.uuid4().hex,
        campaign_id=recipient.campaign_id,
        recipient_id=recipient.recipient_id,
        status="ERROR" if stage == "FAILED" else "SUCCESS",
        provider_status=stage,
        provider_code=recipient.failure_code if stage == "FAILED" else None,
        error_reason=recipient.reason if stage == "FAILED" else None,
    ))


def _lead_details(db: Session, recipient, button_text, clicked_at) -> dict:
    """
    What someone needs in order to call this person back.

    The business behind a recipient is matched by phone where the link was
    never stored, which is the case for every campaign sent before that field
    was carried through.
    """
    from src.models import Business, WhatsAppCampaign

    business = None
    if recipient.business_id:
        business = db.query(Business).filter(
            Business.business_id == recipient.business_id
        ).first()
    if business is None and recipient.phone:
        business = db.query(Business).filter(Business.phone == recipient.phone).first()

    campaign = db.query(WhatsAppCampaign).filter(
        WhatsAppCampaign.campaign_id == recipient.campaign_id
    ).first()

    return {
        "name": recipient.name or (business.name if business else None),
        "phone": recipient.phone,
        "category": business.category if business else None,
        "district": business.district if business else None,
        "state": business.state if business else None,
        "campaign": campaign.name if campaign else None,
        "button_text": button_text,
        "clicked_at": clicked_at.strftime("%d %b %Y, %H:%M UTC") if clicked_at else None,
    }


def _apply_inbound_message(db: Session, message: dict):
    """
    Record a quick-reply button tap.

    Meta sends a tap as an inbound message whose `context.id` is the campaign
    message it answers, which is what ties it back to a recipient. A tap on a
    call-to-action URL button produces no webhook at all — those are only ever
    visible through the tracking-link redirect.
    """
    if (message.get("type") or "") != "button":
        return None

    origin_id = (message.get("context") or {}).get("id")
    if not origin_id:
        return None

    recipient = db.query(WhatsAppCampaignRecipient).filter(
        WhatsAppCampaignRecipient.provider_message_id == origin_id
    ).first()
    if not recipient:
        return None

    inbound_id = message.get("id")
    if inbound_id and db.query(WhatsAppButtonClick).filter(
        WhatsAppButtonClick.provider_message_id == inbound_id
    ).first():
        return None  # already recorded; Meta repeats until acknowledged

    button = message.get("button") or {}
    clicked_at = _parse_ts(message.get("timestamp"))
    db.add(WhatsAppButtonClick(
        click_id=uuid.uuid4().hex,
        campaign_id=recipient.campaign_id,
        recipient_id=recipient.recipient_id,
        button_text=(button.get("text") or None),
        button_payload=(button.get("payload") or None),
        provider_message_id=inbound_id,
        clicked_at=clicked_at,
    ))

    # Somebody has just asked to be contacted, so the details needed to act on
    # that are gathered here rather than left for whoever opens the dashboard
    # next. Returned to the caller, which sends the alert outside the request:
    # Meta redelivers a webhook it does not get a prompt 200 for.
    return _lead_details(db, recipient, button.get("text"), clicked_at)


# --- Webhooks (Phase 18) ---

@router.get("/webhook")
def verify_webhook(
    request: Request,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    """
    Meta API webhook verification endpoint.
    """
    import os
    VERIFY_TOKEN = os.environ.get("META_WEBHOOK_VERIFY_TOKEN", "gmap_scraper_verify_token")

    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")

@router.post("/webhook")
async def receive_webhook(request: Request, background: BackgroundTasks,
                          db: Session = Depends(get_db)):
    """
    Receives incoming webhooks from Meta (e.g. message delivery status).
    """
    import os
    import hmac
    import hashlib

    app_secret = os.environ.get("META_APP_SECRET")
    if not app_secret:
        raise HTTPException(status_code=403, detail="Missing Meta App Secret configuration")

    # 1. Read raw request body before JSON parsing
    raw_body = await request.body()

    # 2. Read the signature header
    signature_header = request.headers.get("X-Hub-Signature-256")
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=403, detail="Missing or malformed signature")

    received_signature = signature_header.split("sha256=")[1]

    # 4. Calculate HMAC-SHA256 using META_APP_SECRET
    expected_signature = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    # 5. Compare signatures safely
    if not hmac.compare_digest(expected_signature, received_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    leads: list = []

    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for status in value.get("statuses", []):
                    _apply_status_event(db, status)
                for message in value.get("messages", []):
                    lead = _apply_inbound_message(db, message)
                    if lead:
                        leads.append(lead)
        db.commit()

        # After the commit and outside the response: a slow mail server must
        # not delay the 200 Meta is waiting for, or it redelivers the event.
        for lead in leads:
            background.add_task(
                notifier.notify_button_click, auth_service.BOOTSTRAP_ADMIN, lead
            )

    except Exception as e:
        logger.error(f"Error processing webhook payload: {str(e)}")
        db.rollback()

    # Meta redelivers anything it does not get a 200 for, so this acknowledges
    # even a payload that could not be applied; the error is in the logs.
    return {"status": "ok"}


# Meta accepts a free-form message only within 24 hours of the recipient's
# last message to us. A tap is a message, so the tap starts the clock.
REPLY_WINDOW = timedelta(hours=24)


def _aware(value: datetime) -> datetime:
    """Read a stored timestamp as UTC. SQLite hands back a naive one."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class ReplyResponse(BaseModel):
    """A free-form message already sent back to this person."""
    reply_id: str
    body: str
    status: str
    error_reason: Optional[str] = None
    sent_by: Optional[str] = None
    sent_at: datetime


class SpendBreakdown(BaseModel):
    category: str
    billable_messages: int
    net: float
    gst: float
    total: float


class SpendResponse(BaseModel):
    """What outreach has cost, ours and Meta's."""
    currency: str = "INR"
    # Summed from our own campaign records.
    billable_messages: int = 0
    net: float = 0.0
    gst: float = 0.0
    total: float = 0.0
    by_category: List[SpendBreakdown] = []
    # Campaigns priced off accepted sends because Meta never reported on
    # them. Their share of the total is a ceiling, and saying so is the
    # difference between a figure that can be trusted and one that cannot.
    estimated_from_sends: int = 0
    # Meta's own billed figure for the window, when it can be reached. This
    # is the authoritative number; ours exists to break it down per campaign.
    meta_total: Optional[float] = None
    meta_days: Optional[int] = None
    meta_error: Optional[str] = None


@router.get("/spend", response_model=SpendResponse)
def get_spend(
    meta_days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """
    Total outreach spend, by category, plus Meta's own billed figure.

    Meta reports cost by day and category but not by campaign, so the
    per-campaign split has to come from our delivery records. Both are
    returned rather than one: a gap between them means our records are
    incomplete, which is worth seeing rather than hiding behind one number.
    """
    campaigns = _with_visits(
        db, db.query(WhatsAppCampaign).order_by(WhatsAppCampaign.created_at.desc()).all()
    )

    out = SpendResponse()
    per_category: dict = {}
    for c in campaigns:
        if not c.billable_messages:
            continue
        out.billable_messages += c.billable_messages
        out.net = round(out.net + c.cost_net, 2)
        out.gst = round(out.gst + c.cost_gst, 2)
        out.total = round(out.total + c.cost_total, 2)
        if c.cost_basis == "sent":
            out.estimated_from_sends += 1

        key = c.billing_category or pricing.DEFAULT_CATEGORY
        agg = per_category.setdefault(key, {"m": 0, "n": 0.0, "g": 0.0, "t": 0.0})
        agg["m"] += c.billable_messages
        agg["n"] = round(agg["n"] + c.cost_net, 2)
        agg["g"] = round(agg["g"] + c.cost_gst, 2)
        agg["t"] = round(agg["t"] + c.cost_total, 2)

    out.by_category = [
        SpendBreakdown(category=k, billable_messages=v["m"],
                       net=v["n"], gst=v["g"], total=v["t"])
        for k, v in sorted(per_category.items(), key=lambda kv: -kv[1]["t"])
    ]

    out.meta_days = meta_days
    try:
        service = MetaWhatsAppService()
        billed = service.billed_total(days=meta_days)
        out.meta_total = billed.get("total")
        if billed.get("error"):
            out.meta_error = billed["error"]
    except Exception as exc:  # a missing figure must not fail the page
        logger.warning(f"spend: could not read Meta billing: {exc}")
        out.meta_error = "Could not reach Meta for the billed total"

    return out


class LeadResponse(BaseModel):
    """Someone who tapped a quick-reply button, and what is needed to call them."""
    click_id: str
    name: Optional[str] = None
    phone: Optional[str] = None
    category: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    campaign: Optional[str] = None
    button_text: Optional[str] = None
    clicked_at: datetime
    # When a typed reply stops being possible. Sent so the panel can say so
    # before someone writes a message that cannot go out.
    window_expires_at: datetime
    replies: List[ReplyResponse] = []


class ReplyRequest(BaseModel):
    message: str


@router.get("/leads", response_model=List[LeadResponse])
def list_leads(limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_db)):
    """
    Recent quick-reply taps, newest first.

    These are people who asked to be contacted, so the row carries everything
    needed to act on it rather than an id to go and look up.

    Meta reports nothing when a call-to-action URL button is tapped, so only
    quick replies appear here; URL taps are counted as link visits instead.
    """
    from src.models import Business

    clicks = (
        db.query(WhatsAppButtonClick)
        .order_by(WhatsAppButtonClick.clicked_at.desc())
        .limit(limit)
        .all()
    )
    if not clicks:
        return []

    recipients = {
        r.recipient_id: r
        for r in db.query(WhatsAppCampaignRecipient).filter(
            WhatsAppCampaignRecipient.recipient_id.in_(
                [c.recipient_id for c in clicks if c.recipient_id]
            )
        ).all()
    }
    campaigns = {
        c.campaign_id: c.name
        for c in db.query(WhatsAppCampaign).filter(
            WhatsAppCampaign.campaign_id.in_([c.campaign_id for c in clicks])
        ).all()
    }

    # Matched on phone as well: recipients created before business_id was
    # carried through have no link, which is every campaign so far.
    phones = [r.phone for r in recipients.values() if r.phone]
    businesses = {}
    if phones:
        for b in db.query(Business).filter(Business.phone.in_(phones)).all():
            businesses.setdefault(b.phone, b)

    replies = {}
    for rep in db.query(WhatsAppReply).filter(
        WhatsAppReply.click_id.in_([c.click_id for c in clicks])
    ).order_by(WhatsAppReply.sent_at.asc()).all():
        replies.setdefault(rep.click_id, []).append(ReplyResponse(
            reply_id=rep.reply_id, body=rep.body, status=rep.status,
            error_reason=rep.error_reason, sent_by=rep.sent_by, sent_at=rep.sent_at,
        ))

    out = []
    for c in clicks:
        r = recipients.get(c.recipient_id)
        b = businesses.get(r.phone) if r else None
        out.append(LeadResponse(
            click_id=c.click_id,
            name=(r.name if r else None) or (b.name if b else None),
            phone=r.phone if r else None,
            category=b.category if b else None,
            district=b.district if b else None,
            state=b.state if b else None,
            campaign=campaigns.get(c.campaign_id),
            button_text=c.button_text,
            clicked_at=c.clicked_at,
            window_expires_at=_aware(c.clicked_at) + REPLY_WINDOW,
            replies=replies.get(c.click_id, []),
        ))
    return out


@router.post("/leads/{click_id}/reply", response_model=ReplyResponse)
def reply_to_lead(
    click_id: str,
    payload: ReplyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Answers a quick-reply tap with a typed message, from the business number.

    This is a plain message rather than a template, which Meta allows only
    inside the 24 hours after the tap. The window is checked here so the
    caller is refused with a reason it can show, instead of Meta's 131047.

    A send that Meta refuses is still recorded, with its reason: a reply that
    silently failed is worse than one visibly marked failed.
    """
    body = (payload.message or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Message is empty")
    # Meta's own ceiling for a text message body.
    if len(body) > 4096:
        raise HTTPException(status_code=400, detail="Message is longer than 4096 characters")

    click = db.query(WhatsAppButtonClick).filter(
        WhatsAppButtonClick.click_id == click_id
    ).first()
    if not click:
        raise HTTPException(status_code=404, detail="No such callback request")

    recipient = db.query(WhatsAppCampaignRecipient).filter(
        WhatsAppCampaignRecipient.recipient_id == click.recipient_id
    ).first()
    phone = recipient.phone if recipient else None
    if not phone:
        raise HTTPException(status_code=409, detail="This request has no phone number to reply to")

    expires = _aware(click.clicked_at) + REPLY_WINDOW
    if datetime.now(timezone.utc) >= expires:
        raise HTTPException(
            status_code=409,
            detail=("The 24-hour reply window closed at "
                    f"{expires.strftime('%d %b, %H:%M UTC')}. "
                    "Only an approved template can reach this number now."),
        )

    meta = MetaWhatsAppService()
    ok, provider_id, _status, error, _code = meta.send_text_message(phone, body)

    reply = WhatsAppReply(
        reply_id=uuid.uuid4().hex,
        click_id=click.click_id,
        phone=phone,
        body=body,
        status="SENT" if ok else "FAILED",
        provider_message_id=provider_id,
        error_reason=None if ok else (error or "Unknown error")[:500],
        sent_by=user.email,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)

    if not ok:
        raise HTTPException(status_code=502, detail=reply.error_reason)

    return ReplyResponse(
        reply_id=reply.reply_id, body=reply.body, status=reply.status,
        error_reason=reply.error_reason, sent_by=reply.sent_by, sent_at=reply.sent_at,
    )
