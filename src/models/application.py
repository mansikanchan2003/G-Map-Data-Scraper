from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func

from src.database import Base


class ApplicationComment(Base):
    """A note the team adds to an application; the applicant never sees it."""
    __tablename__ = "application_comments"

    comment_id = Column(String(32), primary_key=True)
    phone = Column(String(20), ForeignKey("whatsapp_conversations.phone", ondelete="CASCADE"),
                   nullable=False, index=True)
    body = Column(Text, nullable=False)
    author = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ApplicationRemoval(Base):
    """
    An application taken off the Applications tab.

    Only the listing goes: the conversation, its messages and the uploaded
    documents stay, so the Inbox is untouched and Restore brings it back.
    """
    __tablename__ = "application_removals"

    phone = Column(String(20), ForeignKey("whatsapp_conversations.phone", ondelete="CASCADE"),
                   primary_key=True)
    removed_by = Column(String(200), nullable=False)
    removed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
