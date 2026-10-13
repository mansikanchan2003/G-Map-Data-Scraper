from sqlalchemy import Column, String, DateTime, func
from src.database import Base


class SbiBranch(Base):
    """
    An SBI branch whose area is targeted for CSP operators.

    The branch's PIN code is a target location like any other (see Location);
    this keeps the branch details the bank gave alongside it, so the
    Configuration page can show which branch each of those PINs serves.
    """
    __tablename__ = "sbi_branches"

    branch_code = Column(String(10), primary_key=True)
    branch_name = Column(String(120), nullable=False)
    ifsc = Column(String(11), nullable=True)
    pincode = Column(String(10), nullable=False, index=True)
    town = Column(String(120), nullable=True)
    district = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    tehsil = Column(String(100), nullable=True)
    address = Column(String(300), nullable=True)
    # The bank's own hierarchy, as given in its branch lists.
    circle = Column(String(60), nullable=True)
    network = Column(String(20), nullable=True)
    module = Column(String(60), nullable=True)
    region = Column(String(20), nullable=True)
    # Anything to know about where the PIN came from, e.g. a corrected typo.
    note = Column(String(300), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
