from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, func

from src.database import Base


class WhatsAppConversation(Base):
    """
    One row per phone number that has written to the business number.

    The inbox lists these. It also holds where the onboarding bot is with this
    person, because the bot's next move depends only on the last thing it
    asked: a PIN code typed while it waits for one means something different
    from the same digits sent at any other time.
    """
    __tablename__ = "whatsapp_conversations"

    # E.164 with the plus, the form campaign recipients are stored in, so a
    # thread can be joined to the campaigns that reached the same number.
    phone = Column(String(20), primary_key=True, index=True)
    # The name the person set in WhatsApp, as Meta reports it.
    profile_name = Column(String(200), nullable=True)

    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)
    # Meta accepts a free-form message only within 24 hours of this.
    last_inbound_at = Column(DateTime(timezone=True), nullable=True)
    # Inbound messages after this are unread.
    last_read_at = Column(DateTime(timezone=True), nullable=True)

    # The onboarding bot. A step of NULL means it has never been started here.
    bot_step = Column(String(40), nullable=True, index=True)
    bot_data = Column(JSON, nullable=True)
    # Set when someone takes the conversation over by hand, so the bot does
    # not answer across them.
    bot_paused = Column(Boolean, nullable=False, default=False, server_default="0")
    bot_updated_at = Column(DateTime(timezone=True), nullable=True)

    # The document upload link sent to this person. Unguessable, because the
    # page behind it is public: the person filling it in has no account.
    upload_token = Column(String(64), nullable=True, unique=True, index=True)
    upload_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    documents_submitted_at = Column(DateTime(timezone=True), nullable=True)
    # The Google Drive folder this person's documents were copied into.
    drive_folder_url = Column(String(500), nullable=True)

    # A question the bot could not answer, waiting for a person. Cleared only
    # by someone pressing "Question resolved" after answering it, never by
    # the bot and never by a reply alone: a reply may not settle it.
    needs_attention = Column(Boolean, nullable=False, default=False, server_default="0", index=True)
    attention_reason = Column(String(500), nullable=True)
    attention_at = Column(DateTime(timezone=True), nullable=True)
    attention_resolved_by = Column(String(200), nullable=True)
    attention_resolved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class WhatsAppMessage(Base):
    """
    Every message in a conversation, in either direction.

    Campaign sends are not copied here: they are already rows in
    whatsapp_campaign_recipients, and the thread reads them from there.
    """
    __tablename__ = "whatsapp_messages"

    message_id = Column(String(32), primary_key=True, index=True)
    phone = Column(String(20), ForeignKey("whatsapp_conversations.phone", ondelete="CASCADE"),
                   nullable=False, index=True)

    direction = Column(String(3), nullable=False)  # IN, OUT
    # text, button (a template quick reply), interactive (a reply to one of
    # our buttons), image, document, audio, video, location, ... for IN;
    # text, buttons, link for OUT.
    kind = Column(String(20), nullable=False, default="text")
    body = Column(Text, nullable=True)
    # A tapped button's id or payload, or for OUT the buttons offered:
    # [{"id": ..., "title": ...}] or {"text": ..., "url": ...}.
    payload = Column(JSON, nullable=True)

    # Meta's id. Unique so a redelivered webhook is recorded once.
    provider_message_id = Column(String(100), nullable=True, unique=True, index=True)
    # For IN: the id of the message it answers, when it answers one.
    context_id = Column(String(100), nullable=True)

    # OUT only: SENT, DELIVERED, READ, FAILED.
    status = Column(String(20), nullable=True)
    error_reason = Column(String(500), nullable=True)
    # "bot", or the email of whoever typed it.
    sent_by = Column(String(200), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class OnboardingDocument(Base):
    """A file uploaded through the onboarding link. One per document type, replaced on re-upload."""
    __tablename__ = "onboarding_documents"

    document_id = Column(String(32), primary_key=True, index=True)
    phone = Column(String(20), ForeignKey("whatsapp_conversations.phone", ondelete="CASCADE"),
                   nullable=False, index=True)
    doc_type = Column(String(40), nullable=False)

    original_name = Column(String(255), nullable=True)
    stored_path = Column(String(500), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)

    # The copy in Google Drive. Once it is there the local file is removed,
    # so identity documents are kept in one place, not two. Until then the
    # local file is what the inbox serves, and the reason it is not in Drive
    # yet is kept here.
    drive_file_id = Column(String(100), nullable=True)
    drive_url = Column(String(500), nullable=True)
    drive_error = Column(String(500), nullable=True)

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
