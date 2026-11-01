from sqlalchemy import JSON, Column, DateTime, Integer, String, func

from src.database import Base


class AuditEntry(Base):
    """
    One change someone made through the app (services/audit): who, what, on
    what, when, and whether it went through. Written by the session middleware
    for every change, never by the model or an agent. Append-only: the app has
    no way to edit or delete a row, and on Postgres a trigger refuses it.
    """
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    actor = Column(String(200), nullable=False, index=True)
    role = Column(String(20), nullable=True)
    action = Column(String(120), nullable=False, index=True)
    method = Column(String(10), nullable=False)
    # The path with any phone number cut to its last four digits.
    path = Column(String(300), nullable=False)
    status = Column(Integer, nullable=False)
    # What the route added: counts, the decision, the reason. Never message text.
    detail = Column(JSON, nullable=True)
