from sqlalchemy import Column, DateTime, String, func

from src.database import Base


class OptOut(Base):
    """
    A number that asked not to be messaged, or should not be (services/opt_out).

    One row a number. No campaign is sent to it, and the bot's reminders and
    follow-ups stop, until it asks again (START, or tapping a campaign button)
    or the team takes it off the list.
    """
    __tablename__ = "opt_outs"

    phone = Column(String(20), primary_key=True)
    # said_stop, disposition, meta (WhatsApp says they stopped marketing messages) or team.
    source = Column(String(20), nullable=False)
    reason = Column(String(300), nullable=True)
    created_by = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
