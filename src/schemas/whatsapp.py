from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime

class WhatsAppAccountBase(BaseModel):
    display_name: Optional[str] = None
    phone_number: str
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None

class WhatsAppAccountCreate(WhatsAppAccountBase):
    pass

class WhatsAppAccountUpdate(BaseModel):
    display_name: Optional[str] = None
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None
    status: Optional[str] = None

class WhatsAppAccountResponse(WhatsAppAccountBase):
    account_id: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class WhatsAppTemplateBase(BaseModel):
    name: str
    meta_template_name: Optional[str] = None
    language_code: Optional[str] = "en_US"
    # As reported by Meta: UTILITY, MARKETING or MARKETING_LITE.
    category: Optional[str] = None
    header_type: Optional[str] = None
    header_content: Optional[str] = None
    body: str
    footer: Optional[str] = None
    buttons: Optional[List[dict]] = None
    status: Optional[str] = "Draft"

class WhatsAppTemplateCreate(WhatsAppTemplateBase):
    # New templates go to Meta for review automatically; a template that is
    # never submitted cannot be sent, which is what produced #132001 before.
    auto_submit: bool = True
    category: Optional[str] = "MARKETING"

class WhatsAppTemplateUpdate(BaseModel):
    name: Optional[str] = None
    meta_template_name: Optional[str] = None
    language_code: Optional[str] = None
    header_type: Optional[str] = None
    header_content: Optional[str] = None
    body: Optional[str] = None
    footer: Optional[str] = None
    buttons: Optional[List[dict]] = None
    status: Optional[str] = None

class WhatsAppTemplateResponse(WhatsAppTemplateBase):
    template_id: str
    # Populated when creation auto-submitted and Meta rejected the submission,
    # so the UI can explain why a template is still a local draft.
    submission_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class WhatsAppTemplateSubmitRequest(BaseModel):
    """Meta requires a category when a template is submitted for review."""
    category: Optional[str] = "MARKETING"


class WhatsAppTemplateSubmitResponse(BaseModel):
    status: str
    meta_template_name: Optional[str] = None
    language_code: Optional[str] = None
    meta_status: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None


class WhatsAppTemplateSyncResponse(BaseModel):
    """Outcome of reconciling local template rows against the Meta WABA."""
    status: str
    checked: int = 0
    updated: int = 0
    error: Optional[str] = None


class WhatsAppContactValidateRequest(BaseModel):
    contacts: List[dict] # Expected dicts with "name" and "phone" keys, optionally "business_id"

class WhatsAppContactValidateResponse(BaseModel):
    total_records: int
    valid_mobile_numbers: int
    invalid_numbers: int
    empty_phone_numbers: int
    landlines: int
    duplicates_removed: int
    final_sendable_contacts: int
    valid_contacts: List[dict] # {name, phone, business_id}
    invalid_contacts: List[dict] # {raw_phone, name, error_reason}

class WhatsAppCampaignPreviewRequest(BaseModel):
    template_id: str
    contact_name: str
    contact_phone: str

class WhatsAppCampaignCreate(BaseModel):
    name: str
    template_id: str
    account_id: str
    data_source_type: str
    contacts: List[dict] # {name, phone, business_id(optional)}

class WhatsAppCampaignResponse(BaseModel):
    campaign_id: str
    name: str
    template_id: Optional[str] = None
    account_id: Optional[str] = None
    data_source_type: str
    status: str
    total_contacts: int
    successful_count: int
    failed_count: int
    skipped_count: int
    pending_count: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Real clicks on this campaign's tracking links.
    # unique_visits  = recipients who opened the link at least once
    # repeated_visits = clicks beyond each recipient's first
    unique_visits: int = 0
    repeated_visits: int = 0
    total_clicks: int = 0

    model_config = {"from_attributes": True}

class WhatsAppCampaignRecipientResponse(BaseModel):
    recipient_id: str
    business_id: Optional[str] = None
    name: Optional[str] = None
    phone: str
    status: str
    reason: Optional[str] = None
    provider_message_id: Optional[str] = None
    updated_at: datetime

    model_config = {"from_attributes": True}

class MetaTemplateInfo(BaseModel):
    """A template as registered in the Meta WhatsApp Business Account."""
    name: str
    language: str
    status: str
    category: Optional[str] = None


class MetaTemplateListResponse(BaseModel):
    status: str
    templates: List[MetaTemplateInfo] = []
    error: Optional[str] = None


class WhatsAppCampaignLogResponse(BaseModel):
    log_id: str
    recipient_id: Optional[str] = None
    status: str
    provider_status: Optional[str] = None
    provider_code: Optional[str] = None
    error_reason: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WhatsAppCampaignLogsResponse(BaseModel):
    """Execution log for one campaign, newest-last."""
    campaign_id: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    total_contacts: int = 0
    successful_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    items: List[WhatsAppCampaignLogResponse] = []
