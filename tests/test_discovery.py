import pytest
import math
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base
from src.models import Location, Category, Job, Business
from src.services.discovery_engine import (
    GoogleMapsDiscoveryEngine,
    build_search_url,
    Selectors
)
from src.services.normalizer import (
    normalize_text,
    normalize_phone,
    normalize_url,
    normalize_address,
    normalize_business_record
)
from src.services.geo_validator import (
    haversine_distance,
    extract_coords_from_url,
    validate_geo_distance
)
from src.services.deduplicator import (
    generate_dedup_key,
    generate_business_id,
    extract_place_id
)
from src.services import job_manager

# 1. Query Generation
def test_query_generation():
    # Valid category and pincode
    url = build_search_url("Airline Ticket Agency", "110001", 28.6304, 77.2177)
    assert "Airline%20Ticket%20Agency%20near%20110001" in url
    assert "@28.6304,77.2177,12z" in url

    # Pincode NOT FOUND should fall back cleanly without "near NOT FOUND"
    url_not_found = build_search_url("ATM", "NOT FOUND", 28.5, 77.2)
    assert "ATM" in url_not_found
    assert "NOT%20FOUND" not in url_not_found
    assert "@28.5,77.2,12z" in url_not_found

# 2. Normalization
def test_normalization():
    # Text
    assert normalize_text("   Axis   Bank  ATM   ") == "Axis Bank ATM"
    assert normalize_text("") is None
    assert normalize_text("   ") is None

    # Phone
    assert normalize_phone("Phone: +91 9876543210") == "+919876543210"
    assert normalize_phone("09876543210") == "+919876543210"
    assert normalize_phone("9876543210") == "+919876543210"
    assert normalize_phone("invalid") is None
    assert normalize_phone("") is None

    # URL
    clean_url = normalize_url("https://www.example.com/store/?utm_source=google&utm_medium=cpc#details")
    assert "utm_source" not in clean_url
    assert clean_url == "https://www.example.com/store#details"
    assert normalize_url("example.com") == "https://example.com"
    assert normalize_url("") is None

    # Address
    assert normalize_address("Address: 123 Main St, Connaught Place") == "123 Main St, Connaught Place"

    # Business Record
    record = {
        "name": "  State Bank of India  ",
        "phone": "Phone: 011 2345 6789",
        "website": "http://sbi.co.in/?utm_ref=1",
        "address": "Loc: Parliament Street, New Delhi",
        "category": "Bank"
    }
    norm = normalize_business_record(record)
    assert norm["name"] == "State Bank of India"
    assert norm["address"] == "Parliament Street, New Delhi"
    assert "utm_ref" not in (norm["website"] or "")

# 3. Geo Validation
def test_geo_validation():
    # Distance between Connaught Place (28.6304, 77.2177) and Karol Bagh (28.6514, 77.1907) is ~3.5km
    dist = haversine_distance(28.6304, 77.2177, 28.6514, 77.1907)
    assert 3.0 < dist < 4.5

    # Same point distance is 0
    assert haversine_distance(28.0, 77.0, 28.0, 77.0) == 0.0

    # Extract coords from URLs
    u1 = "https://www.google.com/maps/place/SBI/@28.6304,77.2177,15z/data=!3d28.6304!4d77.2177"
    lat, lng = extract_coords_from_url(u1)
    assert lat == 28.6304 and lng == 77.2177

    u2 = "https://www.google.com/maps/place/SBI/@28.6304,77.2177,17z"
    lat2, lng2 = extract_coords_from_url(u2)
    assert lat2 == 28.6304 and lng2 == 77.2177

    # 1. Business inside 20km
    valid, d, notes = validate_geo_distance(28.6514, 77.1907, 28.6304, 77.2177, radius_km=20.0)
    assert valid is True
    assert d is not None and d < 20.0
    assert len(notes) == 0

    # 2. Business outside 20km (e.g. Mumbai to Delhi ~1150km)
    invalid, d_far, notes_far = validate_geo_distance(19.0760, 72.8777, 28.6304, 77.2177, radius_km=20.0)
    assert invalid is False
    assert d_far is not None and d_far > 20.0
    assert any("DISTANCE_EXCEEDED" in n for n in notes_far)

    # 3. Missing business coordinates (MUST be invalid, not assumed inside)
    valid_missing, d_none, notes_missing = validate_geo_distance(None, None, 28.6304, 77.2177, radius_km=20.0)
    assert valid_missing is False
    assert d_none is None
    assert any("COORDINATES_UNAVAILABLE" in n for n in notes_missing)

    # 4. Exact boundary condition
    # 20km along meridian from (0.0, 0.0): 1 deg latitude ~ 111.195 km => 20km ~ 0.1798647 deg
    lat_20km = 20.0 / (6371.0 * (math.pi / 180.0)) # exact radians to degrees for 20.0km
    d_exact = haversine_distance(0.0, 0.0, lat_20km, 0.0)
    assert abs(d_exact - 20.0) < 0.0001
    valid_boundary, d_b, _ = validate_geo_distance(lat_20km, 0.0, 0.0, 0.0, radius_km=20.0)
    assert valid_boundary is True
    assert round(d_b, 2) == 20.0

    # Slightly outside boundary (20.05 km)
    lat_just_outside = (20.05) / (6371.0 * (math.pi / 180.0))
    valid_outside, d_out, notes_out = validate_geo_distance(lat_just_outside, 0.0, 0.0, 0.0, radius_km=20.0)
    assert valid_outside is False
    assert d_out > 20.0
    assert any("DISTANCE_EXCEEDED" in n for n in notes_out)

    # 5. Invalid coordinates (out of bounds [-90..90, -180..180] or NaN)
    valid_inv1, _, notes_inv1 = validate_geo_distance(95.0, 77.0, 28.0, 77.0, radius_km=20.0)
    assert valid_inv1 is False
    assert any("INVALID_COORDINATES" in n for n in notes_inv1)

    valid_inv2, _, notes_inv2 = validate_geo_distance(float('nan'), 77.0, 28.0, 77.0, radius_km=20.0)
    assert valid_inv2 is False
    assert any("INVALID_COORDINATES" in n for n in notes_inv2)

# 4. Duplicate Detection
def test_duplicate_detection():
    # Same name and same address must produce same dedup key
    key1 = generate_dedup_key(
        name="Axis Bank ATM",
        address="Block CD, Pitampura, New Delhi",
        phone="011 2734 8181"
    )
    key2 = generate_dedup_key(
        name="Axis Bank ATM Pvt Ltd",
        address="Block CD, Pitampura, New Delhi",
        phone="01127348181"
    )
    assert key1 == key2

    # Place ID takes highest precedence
    key_pid = generate_dedup_key(
        name="Some Name",
        address="Some Address",
        place_id="ChIJgTwKgJcpXDkR_phqZs3R58E"
    )
    assert key_pid == "pid:ChIJgTwKgJcpXDkR_phqZs3R58E"

    # CRITICAL: Same generic name at different locations must NOT collide
    key_loc_a = generate_dedup_key(name="Axis Bank ATM", address="Connaught Place, New Delhi", phone="01123456789")
    key_loc_b = generate_dedup_key(name="Axis Bank ATM", address="MG Road, Gurgaon", phone="01249876543")
    assert key_loc_a != key_loc_b

# 5. Missing Category
def test_missing_category():
    engine = GoogleMapsDiscoveryEngine(headless=True)
    job = {
        "job_id": "test_cat_missing",
        "category": "",
        "pincode": "110001",
        "latitude": 28.6304,
        "longitude": 77.2177
    }
    res = engine.execute_discovery(job)
    assert res["status"] == "failed"
    assert "category" in res["error"].lower()

# 6. Missing Coordinates
def test_missing_coordinates():
    engine = GoogleMapsDiscoveryEngine(headless=True)
    job = {
        "job_id": "test_coords_missing",
        "category": "ATM",
        "pincode": "110001",
        "latitude": None,
        "longitude": 77.2177
    }
    res = engine.execute_discovery(job)
    assert res["status"] == "failed"
    assert "coordinates" in res["error"].lower()

# 7. Invalid Job Coordinates Format
def test_invalid_job_format():
    engine = GoogleMapsDiscoveryEngine(headless=True)
    job = {
        "job_id": "test_invalid_coords",
        "category": "ATM",
        "pincode": "110001",
        "latitude": "not_a_float",
        "longitude": 77.2177
    }
    res = engine.execute_discovery(job)
    assert res["status"] == "failed"
    assert "invalid coordinate" in res["error"].lower()

# 8. Empty Results Handling (Mocked Page)
def test_empty_results_handling():
    engine = GoogleMapsDiscoveryEngine(headless=True)
    mock_page = MagicMock()
    mock_page.locator.return_value.count.side_effect = lambda: 0
    # Make NO_RESULTS match
    def mock_locator(selector):
        loc = MagicMock()
        if selector == Selectors.NO_RESULTS:
            loc.count.return_value = 1
        elif selector == Selectors.CAPTCHA:
            loc.count.return_value = 0
        else:
            loc.count.return_value = 0
            loc.all.return_value = []
        return loc

    mock_page.locator.side_effect = mock_locator

    job = {
        "job_id": "test_empty_results",
        "category": "NonExistentCategoryXYZ123",
        "pincode": "110001",
        "latitude": 28.6304,
        "longitude": 77.2177
    }
    res = engine.execute_discovery(job, page_override=mock_page)
    assert res["status"] == "zero_results"
    assert res["count"] == 0
    assert res["results"] == []

# 9. Individual Listing Failure Resilience (Mocked Page)
def test_individual_listing_failure():
    engine = GoogleMapsDiscoveryEngine(headless=True)
    mock_page = MagicMock()

    # Create 2 cards: one fails on title, second succeeds
    card1 = MagicMock()
    card1.locator.side_effect = Exception("Card 1 DOM parse error")

    card2 = MagicMock()
    title_elem = MagicMock()
    title_elem.count.return_value = 1
    title_elem.get_attribute.side_effect = lambda attr: "Good Business" if attr == "aria-label" else "https://maps.google.com/test2"
    card2.locator.return_value.first = title_elem

    def mock_locator(selector):
        loc = MagicMock()
        if selector == Selectors.LISTING_ITEM:
            loc.all.return_value = [card1, card2]
        elif selector == Selectors.NO_RESULTS or selector == Selectors.CAPTCHA:
            loc.count.return_value = 0
        else:
            loc.count.return_value = 0
        return loc

    mock_page.locator.side_effect = mock_locator

    job = {
        "job_id": "test_listing_resilience",
        "category": "ATM",
        "pincode": "110001",
        "latitude": 28.6304,
        "longitude": 77.2177
    }
    res = engine.execute_discovery(job, page_override=mock_page)
    # One failed card does not terminate the job!
    assert res["count"] == 1
    assert res["results"][0]["name"] == "Good Business"

# 10. Structured Success Response
def test_structured_success_response():
    engine = GoogleMapsDiscoveryEngine(headless=True)
    mock_page = MagicMock()

    card = MagicMock()
    title_elem = MagicMock()
    title_elem.count.return_value = 1
    title_elem.get_attribute.side_effect = lambda attr: "Premier Travels" if attr == "aria-label" else "https://maps.google.com/?cid=12345"
    card.locator.return_value.first = title_elem

    def mock_locator(selector):
        loc = MagicMock()
        if selector == Selectors.LISTING_ITEM:
            loc.all.return_value = [card]
        else:
            loc.count.return_value = 0
        return loc

    mock_page.locator.side_effect = mock_locator

    job = {
        "job_id": "test_success",
        "category": "Travel Agency",
        "pincode": "110001",
        "latitude": 28.6304,
        "longitude": 77.2177
    }
    res = engine.execute_discovery(job, page_override=mock_page)
    assert res["status"] in ("success", "partial")
    assert res["job_id"] == "test_success"
    assert res["count"] == 1
    assert res["results"][0]["name"] == "Premier Travels"
    assert "query" in res

# 11. Structured Failure Response (Navigation Failure)
def test_structured_failure_response():
    engine = GoogleMapsDiscoveryEngine(headless=True)
    mock_page = MagicMock()
    mock_page.goto.side_effect = Exception("Connection refused / Timeout")

    job = {
        "job_id": "test_failed_nav",
        "category": "ATM",
        "pincode": "110001",
        "latitude": 28.6304,
        "longitude": 77.2177
    }
    res = engine.execute_discovery(job, page_override=mock_page)
    assert res["status"] == "failed"
    assert "Timeout" in res["error"] or "Connection refused" in res["error"]
    assert res["count"] == 0
    assert res["results"] == []

# 12. Bounded Retry Behavior & End-to-End Persistence Pipeline
def test_end_to_end_job_execution_and_retries():
    # In-memory test SQLite DB
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Seed test location and category
        loc = Location(
            location_id="loc_test_01",
            pincode="110001",
            latitude=28.6304,
            longitude=77.2177,
            radius_km=20.0
        )
        cat = Category(
            category_id="cat_test_01",
            category_name="ATM"
        )
        job = Job(
            job_id="job_test_01",
            location_id="loc_test_01",
            category_id="cat_test_01",
            status="PENDING",
            search_query="https://google.com/maps/test",
            attempt_count=0
        )
        db.add_all([loc, cat, job])
        db.commit()

        # Mock engine that returns 3 listings: valid, outside 20km, and missing coords
        mock_engine = MagicMock()
        mock_engine.execute_discovery.return_value = {
            "status": "success",
            "job_id": "job_test_01",
            "count": 3,
            "results": [
                {
                    "name": "HDFC Bank ATM",
                    "address": "Connaught Place, New Delhi",
                    "phone": "011 2345 6789",
                    "website": "https://hdfcbank.com",
                    "google_maps_url": "https://maps.google.com/place1",
                    "place_id": "ChIJ_test_hdfc",
                    "latitude": 28.6310,
                    "longitude": 77.2180,
                    "category": "ATM"
                },
                {
                    "name": "Mumbai ATM Far Away",
                    "address": "Nariman Point, Mumbai",
                    "phone": "022 9876 5432",
                    "website": "https://bank.com",
                    "google_maps_url": "https://maps.google.com/place_far",
                    "place_id": "ChIJ_test_far",
                    "latitude": 19.0760,
                    "longitude": 72.8777,
                    "category": "ATM"
                },
                {
                    "name": "No Coordinates ATM",
                    "address": "Unknown location",
                    "phone": "011 1111 2222",
                    "website": None,
                    "google_maps_url": "https://maps.google.com/place_nocoords",
                    "place_id": "ChIJ_test_nocoords",
                    "latitude": None,
                    "longitude": None,
                    "category": "ATM"
                }
            ]
        }

        # First run: should persist businesses and complete job
        res = job_manager.execute_single_job("job_test_01", db, custom_engine=mock_engine)
        assert res["status"] == "success"
        assert res["businesses_saved"] == 3
        
        # Verify DB state
        saved_job = db.query(Job).filter(Job.job_id == "job_test_01").first()
        assert saved_job.status == "COMPLETED"
        assert saved_job.attempt_count == 1
        assert saved_job.businesses_saved == 3

        businesses = db.query(Business).filter(Business.job_id == "job_test_01").all()
        assert len(businesses) == 3

        # HDFC Bank ATM is inside 20km -> is_valid must be True
        hdfc = db.query(Business).filter(Business.name == "HDFC Bank ATM").first()
        assert hdfc.is_valid is True
        assert hdfc.distance_km is not None and hdfc.distance_km < 20.0

        # Mumbai ATM is ~1150km away -> is_valid must be False
        far_biz = db.query(Business).filter(Business.name == "Mumbai ATM Far Away").first()
        assert far_biz.is_valid is False
        assert far_biz.distance_km > 20.0
        assert "DISTANCE_EXCEEDED" in far_biz.validation_errors

        # No Coordinates ATM has no coords -> is_valid must be False (NOT assumed inside)
        nocoord_biz = db.query(Business).filter(Business.name == "No Coordinates ATM").first()
        assert nocoord_biz.is_valid is False
        assert nocoord_biz.distance_km is None
        assert "COORDINATES_UNAVAILABLE" in nocoord_biz.validation_errors

        # Second run with same mock: test deduplication at DB level (businesses_saved should be 0 new)
        res_dup = job_manager.execute_single_job("job_test_01", db, custom_engine=mock_engine)
        assert res_dup["status"] == "success"
        assert res_dup["businesses_saved"] == 0 # all 3 were duplicates
        assert db.query(Business).count() == 3 # total count did NOT increase

        # Test retry logic
        retry_res = job_manager.retry_job("job_test_01", db)
        assert retry_res["new_status"] == "PENDING"
        assert retry_res["attempt_count"] == 2 # bounded attempt count preserved

    finally:
        db.close()
