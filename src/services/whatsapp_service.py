import uuid
import time
import os
import re
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import logging

from src.models.whatsapp import (
    WhatsAppCampaign, WhatsAppCampaignRecipient,
    WhatsAppCampaignLog, WhatsAppTemplate
)
from src.services.whatsapp_normalizer import WhatsAppNormalizer
from src.services.meta_whatsapp_service import MetaWhatsAppService

logger = logging.getLogger("gmap_scraper.whatsapp_campaign")

# Named placeholders a template body may use, in the order Meta will see them
# as {{1}}, {{2}}. Order matters: Meta matches parameters positionally, so the
# sequence here must be the sequence used when sending.
TEMPLATE_PLACEHOLDERS = ("{{name}}", "{{link}}")


def ordered_placeholders(body: str) -> list:
    """Placeholders present in a body, ordered by where they first appear."""
    found = [(body.index(ph), ph) for ph in TEMPLATE_PLACEHOLDERS if ph in (body or "")]
    return [ph for _pos, ph in sorted(found)]


def tracking_link_for(token: str) -> str:
    """
    The per-recipient link that records a click and forwards to the campaign
    destination. Returns the plain destination when no public base URL is
    configured, so messages still carry a working link before the redirect is
    reachable from the internet.
    """
    base = (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
    target = os.environ.get(
        "CAMPAIGN_LINK_TARGET_URL", "https://kiosk.eko.in/?utm_source=WhatsApp+Campaign"
    )
    if not base or not token:
        return target
    return f"{base}/r/{token}"


def meta_template_name_for(local_name: str) -> str:
    """
    Meta template names must match ^[a-z0-9_]+$, so a display name like
    "Diwali Offer 2026" cannot be used as-is.
    """
    cleaned = re.sub(r"[^a-z0-9]+", "_", (local_name or "").lower()).strip("_")
    return (cleaned or "template")[:512]


def build_meta_components(template, header_handle: str = None) -> list:
    """
    Translates a local template row into the component list Meta expects when
    a template is submitted for review.

    Two differences from how the template is stored locally:
      * Meta uses positional placeholders ({{1}}), not named ones ({{name}}).
      * A media header must carry an example handle from the resumable upload.
    """
    components = []

    header_type = (template.header_type or "NONE").upper()
    if header_type in ("IMAGE", "VIDEO", "DOCUMENT"):
        header = {"type": "HEADER", "format": header_type}
        if header_handle:
            header["example"] = {"header_handle": [header_handle]}
        components.append(header)
    elif header_type == "TEXT" and template.header_content:
        components.append({"type": "HEADER", "format": "TEXT",
                           "text": template.header_content})

    body_text = template.body or ""
    placeholders = ordered_placeholders(body_text)
    if placeholders:
        examples = []
        for index, placeholder in enumerate(placeholders, start=1):
            body_text = body_text.replace(placeholder, "{{%d}}" % index)
            examples.append(
                "Sample Business" if placeholder == "{{name}}"
                else "https://example.com/r/abc123"
            )
        components.append({"type": "BODY", "text": body_text,
                           "example": {"body_text": [examples]}})
    else:
        components.append({"type": "BODY", "text": body_text})

    if template.footer:
        components.append({"type": "FOOTER", "text": template.footer})

    buttons = []
    for btn in (template.buttons or []):
        btn_type = btn.get("type")
        if btn_type == "QUICK_REPLY":
            buttons.append({"type": "QUICK_REPLY", "text": btn.get("text")})
        elif btn_type == "URL":
            buttons.append({"type": "URL", "text": btn.get("text"),
                            "url": btn.get("url")})
    if buttons:
        components.append({"type": "BUTTONS", "buttons": buttons})

    return components


class WhatsAppTemplateSubmissionService:
    """Submits a locally-composed template to Meta for approval."""

    def __init__(self, db: Session):
        self.db = db
        self.meta_service = MetaWhatsAppService()

    def submit(self, template, category: str = "MARKETING") -> dict:
        meta_name = template.meta_template_name or meta_template_name_for(template.name)
        language = template.language_code or "en_US"

        # A media header needs an example handle, produced by uploading the
        # local file through Meta's resumable upload endpoint.
        header_handle = None
        header_type = (template.header_type or "NONE").upper()
        if header_type in ("IMAGE", "VIDEO", "DOCUMENT"):
            if not template.header_content:
                return {"status": "failed",
                        "error": f"Template has header type {header_type} but no media attached."}

            try:
                header_data = json.loads(template.header_content)
            except (ValueError, TypeError):
                header_data = {"source_type": "url", "url": template.header_content}

            if header_data.get("source_type") == "upload":
                media_id = header_data.get("media_id")
                local_path = os.path.join("data", "whatsapp_media", os.path.basename(media_id or ""))
                upload = self.meta_service.upload_resumable(local_path)
                if upload["status"] != "success":
                    return {"status": "failed", "error": upload["error"]}
                header_handle = upload["handle"]
            else:
                return {"status": "failed",
                        "error": "Template submission needs an uploaded media file; a URL header cannot be used as the approval example."}

        components = build_meta_components(template, header_handle)

        logger.info(
            f"whatsapp_template event=TEMPLATE_SUBMIT_STARTED template_id={template.template_id} "
            f"meta_name={meta_name} language={language} category={category}"
        )

        result = self.meta_service.create_message_template(
            name=meta_name, language=language, category=category, components=components
        )

        if result["status"] != "success":
            # 2388024 means a template with this name+language already exists in
            # the WABA -- typically a re-submit, or one created directly in the
            # Meta console. The local row just needs to be pointed at it;
            # failing here would leave a template that can never be sent.
            if result.get("error_subcode") == 2388024:
                existing = self.meta_service.find_approved_template(meta_name, language)
                template.meta_template_name = meta_name
                template.language_code = language
                template.status = "APPROVED" if existing.get("ok") else "PENDING"
                self.db.commit()
                logger.info(
                    f"whatsapp_template event=TEMPLATE_ALREADY_ON_META "
                    f"template_id={template.template_id} meta_name={meta_name} "
                    f"status={template.status}"
                )
                return {"status": "success", "meta_template_name": meta_name,
                        "language_code": language, "meta_status": template.status,
                        "id": None, "note": "Template already existed in Meta; linked to it."}

            logger.error(
                f"whatsapp_template event=TEMPLATE_SUBMIT_FAILED template_id={template.template_id} "
                f"error={result['error']}"
            )
            return {"status": "failed", "error": result["error"],
                    "error_code": result.get("error_code")}

        # Record what Meta now knows this template as, so sending resolves it.
        template.meta_template_name = meta_name
        template.language_code = language
        template.category = (category or "MARKETING").upper()
        # Meta returns the review state on submit; store its wording so the
        # dashboard and the Meta console never disagree.
        template.status = (result.get("template_status") or "PENDING").upper()
        self.db.commit()

        logger.info(
            f"whatsapp_template event=TEMPLATE_SUBMITTED template_id={template.template_id} "
            f"meta_name={meta_name} meta_status={result.get('template_status')}"
        )
        return {"status": "success", "meta_template_name": meta_name,
                "language_code": language,
                "meta_status": result.get("template_status"), "id": result.get("id")}


class WhatsAppTemplateEditService:
    """Sends an edited local template back to Meta so sends actually change."""

    def __init__(self, db: Session):
        self.db = db
        self.meta_service = MetaWhatsAppService()

    def push(self, template) -> dict:
        if not template.meta_template_name:
            return {"status": "skipped",
                    "error": "Template has not been submitted to Meta yet, so there is nothing to update."}

        language = template.language_code or "en_US"
        meta_id = self.meta_service.find_template_id(template.meta_template_name, language)
        if not meta_id:
            return {"status": "failed",
                    "error": f"Could not find '{template.meta_template_name}' ({language}) in the WhatsApp Business Account."}

        # Media headers need a fresh example handle on every edit.
        header_handle = None
        header_type = (template.header_type or "NONE").upper()
        if header_type in ("IMAGE", "VIDEO", "DOCUMENT") and template.header_content:
            try:
                header_data = json.loads(template.header_content)
            except (ValueError, TypeError):
                header_data = {"source_type": "url", "url": template.header_content}
            if header_data.get("source_type") == "upload":
                media_id = header_data.get("media_id")
                local_path = os.path.join("data", "whatsapp_media", os.path.basename(media_id or ""))
                upload = self.meta_service.upload_resumable(local_path)
                if upload["status"] != "success":
                    return {"status": "failed", "error": upload["error"]}
                header_handle = upload["handle"]

        components = build_meta_components(template, header_handle)
        result = self.meta_service.update_message_template(
            meta_id, components, category=template.category
        )

        if result["status"] != "success":
            logger.error(
                f"whatsapp_template event=TEMPLATE_EDIT_FAILED "
                f"template_id={template.template_id} error={result['error']}"
            )
            return {"status": "failed", "error": result["error"]}

        # An edit sends the template back through review.
        template.status = "PENDING"
        self.db.commit()
        logger.info(
            f"whatsapp_template event=TEMPLATE_EDIT_PUSHED template_id={template.template_id} "
            f"meta_name={template.meta_template_name}"
        )
        return {"status": "success", "meta_status": "PENDING"}


class WhatsAppCampaignService:
    def __init__(self, db: Session):
        self.db = db
        self.meta_service = MetaWhatsAppService()

    def create_campaign_and_recipients(self, name: str, template_id: str, account_id: str, data_source_type: str, contacts: list) -> WhatsAppCampaign:
        """
        Creates a new campaign in PENDING state and processes all contacts.
        Normalizes and deduplicates contacts before saving them as recipients.
        """
        campaign_id = uuid.uuid4().hex

        campaign = WhatsAppCampaign(
            campaign_id=campaign_id,
            name=name,
            template_id=template_id,
            account_id=account_id,
            data_source_type=data_source_type,
            status="PENDING",
            total_contacts=len(contacts),
            successful_count=0,
            failed_count=0,
            skipped_count=0,
            pending_count=0
        )
        self.db.add(campaign)
        self.db.flush() # get the ID ready

        seen_phones = set()
        recipients = []
        pending = 0
        skipped = 0

        for c in contacts:
            raw_phone = c.get("phone")
            name = c.get("name")
            business_id = c.get("business_id")

            canonical, error = WhatsAppNormalizer.normalize_phone(raw_phone)

            if error:
                status = "SKIPPED"
                reason = error
                skipped += 1
            else:
                if canonical in seen_phones:
                    status = "SKIPPED"
                    reason = "Duplicate number"
                    skipped += 1
                else:
                    seen_phones.add(canonical)
                    status = "PENDING"
                    reason = None
                    pending += 1

            recipient = WhatsAppCampaignRecipient(
                recipient_id=uuid.uuid4().hex,
                # Own token per recipient: without it a click cannot be
                # attributed, and unique vs repeat visits are unknowable.
                tracking_token=uuid.uuid4().hex,
                campaign_id=campaign_id,
                business_id=business_id,
                name=name,
                phone=canonical or str(raw_phone)[:20], # Save whatever we have if it's invalid
                status=status,
                reason=reason
            )
            recipients.append(recipient)

        self.db.bulk_save_objects(recipients)

        campaign.pending_count = pending
        campaign.skipped_count = skipped

        self.db.commit()
        return campaign

    def execute_campaign(self, campaign_id: str):
        """
        Background task to execute a campaign.
        Iterates over PENDING recipients, calls Meta API, logs results.
        """
        # We need a new session if this is running in a background task
        # But wait, FastAPI BackgroundTasks doesn't automatically give a new session.
        # The caller should ideally pass the campaign_id, and we should create a session.
        # Since we are given `self.db`, if the original request closed it, this will fail.
        # Let's import SessionLocal to be safe.
        from src.database import SessionLocal

        db = SessionLocal()
        try:
            # Atomic Campaign Claim
            updated = db.query(WhatsAppCampaign)\
                .filter(WhatsAppCampaign.campaign_id == campaign_id, WhatsAppCampaign.status == "PENDING")\
                .update({"status": "RUNNING", "started_at": datetime.now(timezone.utc)}, synchronize_session=False)
            db.commit()

            if updated == 0:
                logger.info(f"Campaign {campaign_id} already claimed or not pending.")
                return

            campaign = db.query(WhatsAppCampaign).filter(WhatsAppCampaign.campaign_id == campaign_id).first()
            if not campaign:
                return

            def fail_campaign(reason: str, provider_code: str = None):
                """
                Abort the campaign without sending, and persist WHY.

                Campaign-level aborts used to reach only the Python logger, which
                left the UI showing FAILED with no recoverable reason. They are
                now written to whatsapp_campaign_logs like any send failure.
                """
                campaign.status = "FAILED"
                campaign.completed_at = datetime.now(timezone.utc)
                db.add(WhatsAppCampaignLog(
                    log_id=uuid.uuid4().hex,
                    campaign_id=campaign_id,
                    recipient_id=None,
                    status="ERROR",
                    provider_status=None,
                    provider_code=provider_code,
                    error_reason=reason,
                    duration_ms=None,
                ))
                db.commit()
                logger.error(f"whatsapp_campaign campaign_id={campaign_id} event=CAMPAIGN_FAILED error={reason}")

            template = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id == campaign.template_id).first()
            if not template:
                fail_campaign("Template not found: the campaign references a template that no longer exists.")
                return

            # Template validation
            if template.header_type in ["IMAGE", "VIDEO"] and not template.header_content:
                fail_campaign(f"Missing required header media for header type {template.header_type}.")
                return

            if template.buttons:
                for btn in template.buttons:
                    if btn.get("type") not in ["QUICK_REPLY", "URL"]:
                        fail_campaign(f"Unsupported button type: {btn.get('type')}.")
                        return

            # --- Meta pre-flight ------------------------------------------------
            # Meta resolves a send by (template name, language) against APPROVED
            # templates in the WABA. Checking once here turns what used to be N
            # separate rejected sends into a single actionable failure.
            meta_template_name = template.meta_template_name or template.name
            language_code = template.language_code or "en_US"

            preflight = self.meta_service.find_approved_template(meta_template_name, language_code)
            if not preflight["ok"]:
                available = ", ".join(preflight.get("available") or []) or "none"
                fail_campaign(
                    f"{preflight['error']} Approved templates available: {available}.",
                    provider_code="132001",
                )
                return

            logger.info(
                f"whatsapp_campaign campaign_id={campaign_id} event=TEMPLATE_VALIDATED "
                f"template={meta_template_name} language={language_code}"
            )

            # --- Header media pre-flight ----------------------------------------
            # The media is uploaded to Meta once per recipient. If it is missing
            # or over Meta's size limit every one of those uploads fails, so it
            # is checked once here and the campaign stops with a usable reason
            # instead of a generic "unexpected error".
            if template.header_type in ("IMAGE", "VIDEO") and template.header_content:
                try:
                    header_check = json.loads(template.header_content)
                except (ValueError, TypeError):
                    header_check = {"source_type": "url", "url": template.header_content}

                if header_check.get("source_type") == "upload":
                    media_id = header_check.get("media_id")
                    media_path = os.path.join("data", "whatsapp_media", os.path.basename(media_id or ""))
                    if not media_id or not os.path.exists(media_path):
                        fail_campaign(
                            f"Header media file is missing on the server ({media_id or 'no file'}). "
                            f"Re-upload the {template.header_type.lower()} in the template and try again."
                        )
                        return

                    limit_mb = 5.0 if template.header_type == "IMAGE" else 16.0
                    size_mb = os.path.getsize(media_path) / 1024 / 1024
                    if size_mb > limit_mb:
                        fail_campaign(
                            f"Header {template.header_type.lower()} is {size_mb:.1f}MB, but WhatsApp "
                            f"allows at most {limit_mb:g}MB. Compress it and re-upload the template media."
                        )
                        return

            # --- Header media: uploaded once, reused for every recipient -------
            # It used to be re-uploaded per recipient, so a 365-contact campaign
            # pushed the same PNG to Meta 365 times. That was slow and gave a
            # transient network error 365 chances to land; one read timeout on
            # upload #201 aborted a whole campaign mid-run.
            shared_header_payload = None
            if template.header_type in ("IMAGE", "VIDEO") and template.header_content:
                media_type = template.header_type.lower()
                try:
                    header_data = json.loads(template.header_content)
                except (ValueError, TypeError):
                    header_data = {"source_type": "url", "url": template.header_content}

                if header_data.get("source_type") == "url":
                    shared_header_payload = {"link": header_data.get("url")}
                else:
                    media_id = header_data.get("media_id")
                    local_path = os.path.join("data", "whatsapp_media", os.path.basename(media_id or ""))
                    meta_media_id = None
                    # A media upload is worth retrying: it is one call for the
                    # whole campaign, so a transient failure here is expensive.
                    for attempt in range(3):
                        meta_media_id = self.meta_service.upload_media(local_path, media_type)
                        if meta_media_id:
                            break
                        if attempt < 2:
                            logger.warning(
                                f"whatsapp_campaign campaign_id={campaign_id} "
                                f"event=MEDIA_UPLOAD_RETRY attempt={attempt + 1}"
                            )
                            time.sleep(2 * (attempt + 1))

                    if not meta_media_id:
                        media_error = getattr(self.meta_service, "last_media_error", None)
                        fail_campaign(
                            "Could not upload the template's header media to Meta"
                            + (f": {media_error}" if media_error else "")
                        )
                        return

                    shared_header_payload = {"id": meta_media_id}

                logger.info(
                    f"whatsapp_campaign campaign_id={campaign_id} event=MEDIA_READY "
                    f"type={template.header_type}"
                )

            # Batch processing
            batch_size = 50
            offset = 0

            while True:
                # Re-fetch campaign to check for cancellation
                db.refresh(campaign)
                if campaign.status == "CANCELLED":
                    logger.info(f"Campaign {campaign_id} was cancelled.")
                    break

                # Atomic recipient claiming
                # To prevent multiple workers processing the same recipient, update them to PROCESSING
                pending_recipients = db.query(WhatsAppCampaignRecipient)\
                    .filter(WhatsAppCampaignRecipient.campaign_id == campaign_id, WhatsAppCampaignRecipient.status == "PENDING")\
                    .with_for_update(skip_locked=True)\
                    .limit(batch_size)\
                    .all()

                if not pending_recipients:
                    break

                recipient_ids = [r.recipient_id for r in pending_recipients]
                db.query(WhatsAppCampaignRecipient)\
                    .filter(WhatsAppCampaignRecipient.recipient_id.in_(recipient_ids))\
                    .update({"status": "PROCESSING"}, synchronize_session=False)
                db.commit()

                # Refetch to get updated objects in current session state
                recipients = db.query(WhatsAppCampaignRecipient)\
                    .filter(WhatsAppCampaignRecipient.recipient_id.in_(recipient_ids))\
                    .all()

                for rec in recipients:
                  # One recipient must never take the campaign down with it:
                  # anything unexpected here fails that recipient and moves on.
                  try:
                    components = []

                    # Header - already uploaded once for this campaign
                    if shared_header_payload:
                        media_type = template.header_type.lower()
                        components.append({
                            "type": "header",
                            "parameters": [
                                {
                                    "type": media_type,
                                    media_type: shared_header_payload
                                }
                            ]
                        })

                    # Body. Parameters are positional, so they are supplied in
                    # the same order the placeholders were registered with Meta.
                    body_placeholders = ordered_placeholders(template.body or "")
                    if body_placeholders:
                        parameters = []
                        for placeholder in body_placeholders:
                            if placeholder == "{{name}}":
                                value = rec.name or "there"
                            else:
                                value = tracking_link_for(rec.tracking_token)
                            parameters.append({"type": "text", "text": value})
                        components.append({"type": "body", "parameters": parameters})

                    # Buttons
                    if template.buttons:
                        for idx, btn in enumerate(template.buttons):
                            btn_type = btn.get("type")
                            if btn_type == "URL":
                                components.append({
                                    "type": "button",
                                    "sub_type": "url",
                                    "index": str(idx),
                                    "parameters": [
                                        {
                                            "type": "text",
                                            "text": btn.get("url") or "url" # If dynamic url variable
                                        }
                                    ]
                                })
                            elif btn_type == "QUICK_REPLY":
                                components.append({
                                    "type": "button",
                                    "sub_type": "quick_reply",
                                    "index": str(idx),
                                    "parameters": [
                                        {
                                            "type": "payload",
                                            "payload": btn.get("text")
                                        }
                                    ]
                                })

                    # Call Meta API with bounded retries
                    max_retries = int(os.environ.get("WHATSAPP_META_MAX_RETRIES", "3"))
                    initial_backoff = float(os.environ.get("WHATSAPP_META_INITIAL_BACKOFF_SECONDS", "1.0"))

                    attempt = 0
                    success, msg_id, status_code, error_reason, provider_code = False, None, None, None, None
                    duration_ms = 0

                    while attempt <= max_retries:
                        attempt += 1
                        start_time = time.time()

                        success, msg_id, status_code, error_reason, provider_code = self.meta_service.send_template_message(
                            to_phone=rec.phone,
                            template_name=meta_template_name,
                            language_code=language_code,
                            components=components
                        )

                        duration_ms += int((time.time() - start_time) * 1000)

                        if success:
                            break

                        is_transient = status_code is None or status_code in ["429", "500", "502", "503", "504"]
                        if not is_transient or attempt > max_retries:
                            break

                        backoff = initial_backoff * (2 ** (attempt - 1))
                        logger.warning(
                            f"Campaign {campaign_id} Recipient {rec.recipient_id} "
                            f"Attempt {attempt} failed (Status: {status_code}, Reason: {error_reason}). "
                            f"Retrying in {backoff}s"
                        )
                        time.sleep(backoff)

                    # Update Recipient
                    if success:
                        rec.status = "SENT"
                        rec.provider_message_id = msg_id
                        # Meta's own "sent" webhook will confirm this, but the
                        # send itself is the first evidence and should not wait
                        # on a webhook that may never be configured.
                        rec.sent_at = datetime.now(timezone.utc)
                        campaign.successful_count += 1
                        campaign.pending_count -= 1
                    else:
                        rec.status = "FAILED"
                        rec.reason = error_reason
                        rec.failed_at = datetime.now(timezone.utc)
                        rec.failure_code = str(provider_code) if provider_code is not None else None
                        campaign.failed_count += 1
                        campaign.pending_count -= 1

                    # Create Log
                    log = WhatsAppCampaignLog(
                        log_id=uuid.uuid4().hex,
                        campaign_id=campaign_id,
                        recipient_id=rec.recipient_id,
                        status="SUCCESS" if success else "ERROR",
                        provider_status=status_code,
                        provider_code=provider_code,
                        error_reason=error_reason,
                        duration_ms=duration_ms
                    )
                    db.add(log)

                    # Respect Meta API rate limits - throttle our sending
                    # If this was real, we would monitor headers like x-ratelimit
                    time.sleep(0.05)

                  except Exception as rec_err:
                    # Contain the blast radius to this one recipient. Before
                    # this, a single transient error (e.g. a read timeout)
                    # propagated out and marked the entire campaign FAILED,
                    # leaving the remaining recipients untouched.
                    logger.exception(
                        f"whatsapp_campaign campaign_id={campaign_id} "
                        f"event=RECIPIENT_SEND_FAILED recipient_id={rec.recipient_id}"
                    )
                    rec.status = "FAILED"
                    rec.reason = f"Unexpected error while sending: {rec_err}"
                    rec.failed_at = datetime.now(timezone.utc)
                    campaign.failed_count += 1
                    campaign.pending_count -= 1
                    db.add(WhatsAppCampaignLog(
                        log_id=uuid.uuid4().hex,
                        campaign_id=campaign_id,
                        recipient_id=rec.recipient_id,
                        status="ERROR",
                        error_reason=str(rec_err),
                    ))

                db.commit()

            if campaign.status != "CANCELLED":
                if campaign.failed_count > 0 and campaign.successful_count == 0:
                    campaign.status = "FAILED"
                elif campaign.failed_count > 0:
                    campaign.status = "PARTIAL"
                else:
                    campaign.status = "COMPLETED"

            campaign.completed_at = datetime.now(timezone.utc)
            db.commit()

        except Exception as e:
            # `campaign` may never have been bound if the failure happened during
            # the claim/lookup, so it is not touched blindly here -- doing so
            # raised NameError and destroyed the original traceback.
            logger.exception(f"whatsapp_campaign campaign_id={campaign_id} event=CAMPAIGN_FAILED")
            try:
                db.rollback()
                db.query(WhatsAppCampaign).filter(
                    WhatsAppCampaign.campaign_id == campaign_id
                ).update(
                    {"status": "FAILED", "completed_at": datetime.now(timezone.utc)},
                    synchronize_session=False,
                )
                db.add(WhatsAppCampaignLog(
                    log_id=uuid.uuid4().hex,
                    campaign_id=campaign_id,
                    recipient_id=None,
                    status="ERROR",
                    error_reason=f"Campaign aborted with an unexpected error: {e}",
                ))
                db.commit()
            except Exception:
                logger.exception(f"Could not persist failure state for campaign {campaign_id}")
        finally:
            db.close()
