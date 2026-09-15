import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session
from src.services.job_manager import execute_single_job
from src.models import Business, Job, Location, Category
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.database import Base

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)

@patch('src.services.job_manager.discovery_engine')
@patch('src.services.email_enricher.EmailEnricher.enrich_batch')
def test_email_enrichment_integration(mock_enrich_batch, mock_discovery, test_db: Session):
    # Setup test data
    loc = Location(location_id="loc1", pincode="12345", latitude=10.0, longitude=20.0, radius_km=5.0)
    cat = Category(category_id="cat1", category_name="Plumbers")
    job = Job(job_id="job1", location_id="loc1", category_id="cat1", status="PENDING", search_query="test")
    test_db.add_all([loc, cat, job])
    test_db.commit()

    # Mock discovery engine
    mock_discovery.execute_discovery.return_value = {
        "status": "success",
        "results": [
            {
                "name": "Plumber 1",
                "phone": "123",
                "website": "http://plumber1.com",
                "google_maps_url": "http://maps/1",
                "latitude": 10.0,
                "longitude": 20.0,
                "place_id": "p1"
            },
            {
                "name": "Plumber 2",
                "phone": "456",
                "website": "http://plumber2.com", # Needs enrichment
                "google_maps_url": "http://maps/2",
                "latitude": 10.0,
                "longitude": 20.0,
                "place_id": "p2"
            }
        ]
    }

    # Setup the business 1 to ALREADY have an email via some mechanism or we just test that Plumber 1 gets skipped.
    # Wait, the job manager creates the businesses. Initially both have NO email.
    
    # Mock the email enricher to return an email for Plumber 2 only
    def mock_enrich(businesses):
        results = []
        for b in businesses:
            if "plumber1" in b["website"]:
                results.append({
                    "business_id": b["business_id"],
                    "email": None,
                    "email_source_url": None,
                    "email_enrichment_status": "not_found"
                })
            else:
                results.append({
                    "business_id": b["business_id"],
                    "email": "info@plumber2.com",
                    "email_source_url": "http://plumber2.com/contact",
                    "email_enrichment_status": "found"
                })
        return results
        
    mock_enrich_batch.side_effect = mock_enrich

    # Execute
    res = execute_single_job("job1", test_db, custom_engine=mock_discovery)

    assert res["status"] == "success"
    assert res["businesses_saved"] == 2

    # Verify Database
    b1 = test_db.query(Business).filter(Business.name == "Plumber 1").first()
    b2 = test_db.query(Business).filter(Business.name == "Plumber 2").first()

    # Plumber 1
    assert b1.website == "http://plumber1.com"
    assert b1.email is None
    assert b1.email_enrichment_status == "not_found"

    # Plumber 2
    assert b2.website == "http://plumber2.com"
    assert b2.email == "info@plumber2.com"
    assert b2.email_source_url == "http://plumber2.com/contact"
    assert b2.email_enrichment_status == "found"
    assert b2.email_enriched_at is not None

@patch('src.services.job_manager.discovery_engine')
@patch('src.services.email_enricher.EmailEnricher.enrich_batch')
def test_existing_email_not_overwritten(mock_enrich_batch, mock_discovery, test_db: Session):
    # Setup test data
    loc = Location(location_id="loc2", pincode="12345", latitude=10.0, longitude=20.0)
    cat = Category(category_id="cat2", category_name="Plumbers")
    job = Job(job_id="job2", location_id="loc2", category_id="cat2", status="PENDING", search_query="test")
    test_db.add_all([loc, cat, job])
    
    from src.services.deduplicator import generate_dedup_key, generate_business_id
    dedup_key = generate_dedup_key(
        name="Existing Plumber",
        address=None,
        phone=None,
        place_id="existing_place",
        maps_url="http://maps/existing"
    )
    biz_id = generate_business_id(
        name="Existing Plumber",
        phone=None,
        lat=None,
        lng=None,
        maps_url="http://maps/existing"
    )
    # Pre-existing business with email
    biz = Business(
        business_id=biz_id,
        job_id="job2",
        name="Existing Plumber",
        website="http://existing.com",
        email="do_not_touch@existing.com",
        category="Plumbers",
        dedup_key=dedup_key,
        source_query="test"
    )
    test_db.add(biz)
    test_db.commit()

    mock_discovery.execute_discovery.return_value = {
        "status": "success",
        "results": [
            {
                "name": "Existing Plumber", # duplicate
                "website": "http://existing.com",
                "google_maps_url": "http://maps/existing",
                "place_id": "existing_place"
            }
        ]
    }
    
    res = execute_single_job("job2", test_db, custom_engine=mock_discovery)
    
    # Enrich batch should NOT have been called with existing plumber
    called_with_existing = False
    if mock_enrich_batch.called:
        args = mock_enrich_batch.call_args[0][0]
        for a in args:
            if a["name"] == "Existing Plumber":
                called_with_existing = True
    assert not called_with_existing
    
    test_db.refresh(biz)
    assert biz.email == "do_not_touch@existing.com"
    assert biz.email_enrichment_status == "skipped_existing_email"

@patch('src.services.job_manager.discovery_engine')
@patch('src.services.email_enricher.EmailEnricher.enrich_batch')
def test_enrichment_failure_does_not_fail_discovery(mock_enrich_batch, mock_discovery, test_db: Session):
    loc = Location(location_id="loc3", pincode="12345", latitude=10.0, longitude=20.0)
    cat = Category(category_id="cat3", category_name="Plumbers")
    job = Job(job_id="job3", location_id="loc3", category_id="cat3", status="PENDING", search_query="test")
    test_db.add_all([loc, cat, job])
    test_db.commit()

    mock_discovery.execute_discovery.return_value = {
        "status": "success",
        "results": [
            {
                "name": "Plumber Fail",
                "website": "http://fail.com",
                "google_maps_url": "http://maps/fail"
            }
        ]
    }
    
    # Force enricher to throw exception
    mock_enrich_batch.side_effect = Exception("Browser crashed")
    
    res = execute_single_job("job3", test_db, custom_engine=mock_discovery)
    
    # Discovery should still be successful and business saved!
    assert res["status"] == "success"
    assert res["businesses_saved"] == 1
    
    b = test_db.query(Business).filter(Business.name == "Plumber Fail").first()
    assert b is not None
    assert b.email is None
