from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Text, func, Integer, JSON
from sqlalchemy.orm import relationship
from src.database import Base

class WhatsAppAccount(Base):
    __tablename__ = "whatsapp_accounts"
    
    account_id = Column(String(32), primary_key=True, index=True)
    display_name = Column(String(200), nullable=True)
    phone_number = Column(String(20), nullable=False, unique=True)
    phone_number_id = Column(String(100), nullable=True)
    waba_id = Column(String(100), nullable=True)
    status = Column(String(50), nullable=False, default="Configuration Pending") # "Configuration Pending", "Connected", "Error"
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class WhatsAppTemplate(Base):
    __tablename__ = "whatsapp_templates"

    template_id = Column(String(32), primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    status = Column(String(50), nullable=False, default="Draft") # Draft, Ready, Submitted, Active, Archived

    # Name of the matching template registered and APPROVED in the Meta WABA.
    # Meta resolves template sends by this name, not by the local display name.
    meta_template_name = Column(String(200), nullable=True)
    # Language code the Meta template was approved under (e.g. en_US, en, en_IN).
    language_code = Column(String(20), nullable=False, default="en_US")
    # Meta's billing category: UTILITY, MARKETING or MARKETING_LITE. It is set
    # by Meta at review time and can differ from what was requested, so it is
    # synced back rather than assumed.
    category = Column(String(40), nullable=True)
    
    header_type = Column(String(50), nullable=True) # NONE, IMAGE, VIDEO, TEXT
    header_content = Column(Text, nullable=True) # URL to media, or text
    
    body = Column(Text, nullable=False)
    footer = Column(String(500), nullable=True)
    
    buttons = Column(JSON, nullable=True) # JSON array of buttons configurations
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)


class WhatsAppCampaign(Base):
    __tablename__ = "whatsapp_campaigns"
    
    campaign_id = Column(String(32), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    
    # Campaign history outlives the template: deleting a template clears the
    # link rather than blocking the delete or erasing the campaign.
    template_id = Column(String(32), ForeignKey("whatsapp_templates.template_id", ondelete="SET NULL"), nullable=True)
    account_id = Column(String(32), ForeignKey("whatsapp_accounts.account_id"), nullable=True)
    
    data_source_type = Column(String(50), nullable=False) # "scraped", "upload"
    status = Column(String(50), nullable=False, default="PENDING") # PENDING, RUNNING, COMPLETED, PARTIAL, FAILED, CANCELLED
    
    total_contacts = Column(Integer, nullable=False, default=0)
    successful_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    pending_count = Column(Integer, nullable=False, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    template = relationship("WhatsAppTemplate")
    account = relationship("WhatsAppAccount")
    recipients = relationship("WhatsAppCampaignRecipient", back_populates="campaign", cascade="all, delete-orphan")


class WhatsAppCampaignRecipient(Base):
    __tablename__ = "whatsapp_campaign_recipients"
    
    recipient_id = Column(String(32), primary_key=True, index=True)
    campaign_id = Column(String(32), ForeignKey("whatsapp_campaigns.campaign_id"), nullable=False, index=True)

    # Opaque per-recipient token used in the tracking link. Attribution is only
    # genuine if each recipient gets their own URL; a link shared by everyone
    # cannot tell who clicked, or separate a unique visitor from a repeat one.
    tracking_token = Column(String(32), nullable=True, unique=True, index=True)
    
    # Using existing business relationships where applicable, but keeping them independent
    business_id = Column(String(16), ForeignKey("businesses.business_id", ondelete="SET NULL"), nullable=True, index=True)
    
    name = Column(String(500), nullable=True)
    phone = Column(String(20), nullable=False, index=True)
    
    status = Column(String(50), nullable=False, default="PENDING") # PENDING, SENDING, SENT, DELIVERED, READ, FAILED, SKIPPED
    reason = Column(Text, nullable=True) # E.g., "Invalid mobile number", "Provider 4xx"
    
    provider_message_id = Column(String(100), nullable=True) # WhatsApp Meta API Message ID
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    campaign = relationship("WhatsAppCampaign", back_populates="recipients")
    business = relationship("Business")


class WhatsAppCampaignLog(Base):
    __tablename__ = "whatsapp_campaign_logs"
    
    log_id = Column(String(32), primary_key=True, index=True)
    campaign_id = Column(String(32), ForeignKey("whatsapp_campaigns.campaign_id"), nullable=False, index=True)
    recipient_id = Column(String(32), ForeignKey("whatsapp_campaign_recipients.recipient_id", ondelete="SET NULL"), nullable=True)
    
    status = Column(String(50), nullable=False)
    provider_status = Column(String(100), nullable=True)
    provider_code = Column(String(50), nullable=True)
    error_reason = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    campaign = relationship("WhatsAppCampaign")


class WhatsAppLinkClick(Base):
    """
    One row per actual click on a campaign's tracking link.

    Rows are only ever written by the redirect endpoint when a real request
    arrives, so counts derived from this table reflect genuine visits rather
    than anything inferred. WhatsApp does not report clicks on links written
    in a message body, which is why the redirect exists at all.
    """
    __tablename__ = "whatsapp_link_clicks"

    click_id = Column(String(32), primary_key=True, index=True)
    campaign_id = Column(String(32), ForeignKey("whatsapp_campaigns.campaign_id"), nullable=False, index=True)
    recipient_id = Column(String(32), ForeignKey("whatsapp_campaign_recipients.recipient_id", ondelete="SET NULL"), nullable=True, index=True)

    target_url = Column(Text, nullable=False)
    # Hashed, never the raw address: enough to spot obvious bot repeats
    # without storing a visitor's IP.
    ip_hash = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)

    clicked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    campaign = relationship("WhatsAppCampaign")
    recipient = relationship("WhatsAppCampaignRecipient")
