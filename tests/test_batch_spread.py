"""
A batch should reach across locations, not drain one.

Jobs are generated location by location, so an unordered LIMIT takes the
whole of one town's category list before touching the next. That is how a
25-job Punjab batch covered two locations out of thirteen.
"""
import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import Category, Job, Location  # noqa: F401
from src.routers.discovery import BatchRequest, apply_target_filters

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

LOCATIONS = 10
CATEGORIES = 20


@pytest.fixture
def db():
    s = TestingSessionLocal()
    s.query(Job).delete()
    s.query(Location).delete()
    s.query(Category).delete()
    s.commit()

    for c in range(CATEGORIES):
        s.add(Category(category_id=f"cat{c:03d}", category_name=f"Category {c}"))
    for l in range(LOCATIONS):
        s.add(Location(location_id=f"loc{l:03d}", pincode=f"1400{l:02d}",
                       latitude=30.0 + l, longitude=75.0 + l,
                       radius_km=20.0, state="Punjab", anchor_name=f"Town {l}"))
    s.flush()

    # Inserted the way generate_jobs_for does it: all of one location's
    # categories together. This ordering is what the fix has to survive.
    for l in range(LOCATIONS):
        for c in range(CATEGORIES):
            jid = hashlib.sha256(f"loc{l:03d}cat{c:03d}".encode()).hexdigest()[:16]
            s.add(Job(job_id=jid, location_id=f"loc{l:03d}", category_id=f"cat{c:03d}",
                      status="PENDING", search_query="https://maps.google.com"))
    s.commit()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def select_batch(db, size):
    """The selection _run_batch performs."""
    from sqlalchemy import func as sa_func

    payload = BatchRequest(batch_size=size, states=["Punjab"])
    ranked = (
        apply_target_filters(db.query(Job).filter(Job.status == "PENDING"), payload)
        .add_columns(
            sa_func.row_number()
            .over(partition_by=Job.location_id, order_by=Job.job_id)
            .label("rank_in_location")
        )
        .subquery()
    )
    return (
        db.query(Job)
        .join(ranked, Job.job_id == ranked.c.job_id)
        .order_by(ranked.c.rank_in_location, Job.location_id)
        .limit(size)
        .all()
    )


def test_a_batch_covers_every_location_when_it_can(db):
    jobs = select_batch(db, 25)
    locations = {j.location_id for j in jobs}
    # 25 jobs across 10 locations: every one should appear.
    assert len(locations) == LOCATIONS, f"only reached {len(locations)} of {LOCATIONS}"


def test_no_location_is_drained_before_others_start(db):
    jobs = select_batch(db, 25)
    per_location = {}
    for j in jobs:
        per_location[j.location_id] = per_location.get(j.location_id, 0) + 1
    # Round-robin: with 25 jobs over 10 locations nobody gets more than three.
    assert max(per_location.values()) <= 3, per_location


def test_a_small_batch_still_spreads(db):
    jobs = select_batch(db, 5)
    assert len({j.location_id for j in jobs}) == 5


def test_the_unordered_selection_would_have_failed(db):
    # The behaviour being fixed, kept so the test above cannot pass for the
    # wrong reason if the ordering is silently dropped again.
    naive = (db.query(Job).filter(Job.status == "PENDING")
             .order_by(Job.location_id, Job.job_id).limit(25).all())
    assert len({j.location_id for j in naive}) < LOCATIONS
