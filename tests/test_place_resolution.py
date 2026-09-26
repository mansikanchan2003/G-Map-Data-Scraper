"""
Geography attached to a user-added location.

Businesses copy their state, district and tehsil straight off the location row,
so a location saved without them produces businesses that can never be filtered
by geography afterwards. These tests pin down where each field is allowed to
come from.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import Location  # noqa: F401  (registers the tables on Base)
from src.services.discovery_engine import parse_place_heading

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


class TestParsePlaceHeading:
    """Maps states the place, and — for a PIN search — the state and the PIN."""

    def test_pincode_search_yields_place_state_and_pin(self):
        assert parse_place_heading("Bhali Anandpur, Haryana 124001") == {
            "place": "Bhali Anandpur",
            "state": "Haryana",
            "pincode": "124001",
        }

    def test_state_that_is_also_the_city(self):
        assert parse_place_heading("New Delhi, Delhi 110001") == {
            "place": "New Delhi",
            "state": "Delhi",
            "pincode": "110001",
        }

    def test_multi_word_state_survives(self):
        parsed = parse_place_heading("Buderna, Uttar Pradesh 244221")
        assert parsed["state"] == "Uttar Pradesh"
        assert parsed["pincode"] == "244221"

    def test_town_search_yields_only_the_town(self):
        # Searching a town name states nothing administrative, and inventing a
        # state from the town name is exactly the guess this must not make.
        assert parse_place_heading("Rohtak") == {
            "place": "Rohtak",
            "state": None,
            "pincode": None,
        }

    @pytest.mark.parametrize("heading", [None, "", "   "])
    def test_no_heading_yields_nothing(self, heading):
        assert parse_place_heading(heading) == {
            "place": None,
            "state": None,
            "pincode": None,
        }

    def test_district_is_never_returned(self):
        # Maps never names the district, so no heading may produce one; it is
        # always the caller's to supply.
        for heading in [
            "Bhali Anandpur, Haryana 124001",
            "New Delhi, Delhi 110001",
            "Rohtak",
        ]:
            assert "district" not in parse_place_heading(heading)


class TestEnsureLocationGeography:
    """A custom location must carry the geography its businesses inherit."""

    def test_caller_values_are_persisted(self, db_session):
        from src.services.custom_target import ensure_location

        result = ensure_location(
            db_session, "Testpur",
            latitude=28.9, longitude=76.5, radius_km=20.0,
            state="Haryana", district="ROHTAK", tehsil="Rohtak",
        )

        location = result["location"]
        assert location.state == "Haryana"
        assert location.district == "ROHTAK"
        assert location.tehsil == "Rohtak"

    def test_blank_geography_is_stored_as_null_not_empty_string(self, db_session):
        # An empty string passes a NOT NULL check but fails every "is it set?"
        # test downstream, so it must not survive as one.
        from src.services.custom_target import ensure_location

        result = ensure_location(
            db_session, "Blankville",
            latitude=28.1, longitude=76.1, radius_km=20.0,
            state="   ", district="", tehsil=None,
        )

        location = result["location"]
        assert location.state is None
        assert location.district is None
        assert location.tehsil is None
