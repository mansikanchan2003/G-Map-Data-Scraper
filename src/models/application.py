from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, String, Text, func

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


class QualifiedLead(Base):
    """
    An applicant who reached Qualified (PIN in our area, nothing ruling them
    out) or Strongly qualified (PIN, 12th or more, can invest), kept for good:
    a later answer, or taking the application off the tab, does not lose it.
    """
    __tablename__ = "qualified_leads"

    phone = Column(String(20), primary_key=True)
    name = Column(String(200), nullable=True)
    # The highest level reached: "Qualified" or "Strongly qualified".
    level = Column(String(60), nullable=False)
    # Why, in plain lines, as of the highest level reached.
    why = Column(JSON, nullable=True)
    qualified_at = Column(DateTime(timezone=True), nullable=True)
    strongly_qualified_at = Column(DateTime(timezone=True), nullable=True)
    pincode = Column(String(10), nullable=True)
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    tehsil = Column(String(100), nullable=True)
    # The nearest SBI branch from our branch list, and how far.
    branch_code = Column(String(10), nullable=True)
    branch_name = Column(String(120), nullable=True)
    branch_ao = Column(String(60), nullable=True)
    branch_region = Column(String(20), nullable=True)
    branch_circle = Column(String(60), nullable=True)
    branch_distance_km = Column(Float, nullable=True)
    branch_checked_pin = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
