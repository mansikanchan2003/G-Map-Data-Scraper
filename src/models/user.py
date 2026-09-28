from sqlalchemy import Column, String, DateTime, func

from src.database import Base


class User(Base):
    """
    Someone who may sign in.

    Signing up does not grant access: a new account sits at PENDING until an
    admin approves it. That is the point of the flow — the address being on
    the company domain proves only that it is a colleague's, not that this
    particular colleague should see campaign data and send messages from the
    company's WhatsApp number.
    """
    __tablename__ = "users"

    user_id = Column(String(32), primary_key=True, index=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=True)
    password_hash = Column(String(255), nullable=False)

    # admin can approve others and see the approvals queue; member cannot.
    role = Column(String(20), nullable=False, default="member")
    # PENDING -> APPROVED | REJECTED, and DISABLED for revoking later.
    status = Column(String(20), nullable=False, default="PENDING", index=True)

    # Who decided, and when — an approval that cannot be traced back to a
    # person is not much of a control.
    decided_by = Column(String(200), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(String(500), nullable=True)

    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
