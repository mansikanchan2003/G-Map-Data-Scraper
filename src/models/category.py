from sqlalchemy import Column, String, DateTime, func
from src.database import Base

class Category(Base):
    __tablename__ = "categories"

    category_id = Column(String(12), primary_key=True, index=True)
    category_name = Column(String(200), nullable=False, unique=True, index=True)
    persona = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
