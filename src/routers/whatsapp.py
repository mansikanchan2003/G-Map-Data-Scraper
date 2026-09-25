from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import uuid
import logging
import os
import shutil
from fastapi.responses import FileResponse
from src.database import get_db
from src.models.whatsapp import (
    WhatsAppAccount, WhatsAppTemplate, WhatsAppCampaign,
    WhatsAppCampaignRecipient, WhatsAppCampaignLog, WhatsAppLinkClick
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
    for key, value in update_data.items():
        setattr(db_tmpl, key, value)

    db.commit()
    db.refresh(db_tmpl)

    # A template's text lives with Meta: a send supplies only the name and
    # parameters, and Meta renders the message from its own copy. Editing
    # locally therefore changes the preview but NOT what recipients receive,
    # so the edit is pushed to Meta rather than left to diverge silently.
    from src.services.whatsapp_service import WhatsAppTemplateEditService

    content_changed = any(
        k in update_data for k in ("body", "footer", "header_type", "header_content", "buttons")
    )
    response = WhatsAppTemplateResponse.model_validate(db_tmpl)

    if content_changed and db_tmpl.meta_template_name:
        result = WhatsAppTemplateEditService(db).push(db_tmpl)
        db.refresh(db_tmpl)
        response = WhatsAppTemplateResponse.model_validate(db_tmpl)
        if result["status"] != "success":
            response.submission_error = (
                f"Saved locally, but Meta did not accept the change: {result['error']} "
                f"Campaigns will keep sending the previously approved text until this succeeds."
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


def _with_visits(db: Session, campaigns: list) -> List[WhatsAppCampaignResponse]:
    counts = _visit_counts(db, [c.campaign_id for c in campaigns])
    out = []
    for c in campaigns:
        item = WhatsAppCampaignResponse.model_validate(c)
        stat = counts.get(c.campaign_id, {})
        item.unique_visits = stat.get("unique", 0)
        item.repeated_visits = stat.get("repeated", 0)
        item.total_clicks = stat.get("total", 0)
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
    query = db.query(WhatsAppCampaignRecipient).filter(WhatsAppCampaignRecipient.campaign_id == campaign_id)
    total = query.count()
    items = query.order_by(WhatsAppCampaignRecipient.created_at.asc()).offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedRecipients(
        items=[WhatsAppCampaignRecipientResponse.model_validate(i) for i in items],
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
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
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

    try:
        # Example processing of message status updates
        # entries = payload.get("entry", [])
        # for entry in entries:
        #     changes = entry.get("changes", [])
        #     for change in changes:
        #         value = change.get("value", {})
        #         statuses = value.get("statuses", [])
        #         for status in statuses:
        #             msg_id = status.get("id")
        #             status_val = status.get("status") # sent, delivered, read, failed
        #
        #             # Find the log and recipient based on provider_message_id
        #             # Update their status accordingly
        pass
    except Exception as e:
        pass

    return {"status": "ok"}
