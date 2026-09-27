from sqlalchemy import Column, String, Text, DateTime, func

from src.database import Base


class AppSetting(Base):
    """
    Small key/value store for things the app discovers about itself at runtime.

    The live Google Sheet is the first of these: its id is created on first
    use, not configured ahead of time, so it has to be written down somewhere
    that survives a restart. An env var cannot hold a value the app itself
    produces.
    """
    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True, index=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
