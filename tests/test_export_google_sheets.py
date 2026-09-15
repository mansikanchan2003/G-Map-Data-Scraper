import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.database import get_db, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid
import os
import base64
import json
from unittest.mock import patch, MagicMock
from src.models import Business

# Test DB Setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_google_sheets.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

client = TestClient(app)

@pytest.fixture(autouse=True)
def override_db_fixture():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Add dummy businesses
    businesses = [
        Business(
            business_id=f"B{uuid.uuid4().hex[:10]}",
            job_id="J123",
            name="Test Biz 1",
            address="123 Test St",
            phone="+919876543210",
            category="Restaurant",
            district="South Delhi",
            state="DELHI",
            source_query="test",
            dedup_key="test1",
            is_valid=True
        ),
        Business(
            business_id=f"B{uuid.uuid4().hex[:10]}",
            job_id="J123",
            name="Test Biz 2",
            address="456 Other Rd",
            phone="011-23456789",
            category="Cafe",
            district="North Delhi",
            state="DELHI",
            source_query="test",
            dedup_key="test2",
            is_valid=True
        ),
        Business(
            business_id=f"B{uuid.uuid4().hex[:10]}",
            job_id="J123",
            name="Test Invalid",
            address="None",
            phone=None,
            category="Bar",
            district="South Delhi",
            state="DELHI",
            source_query="test",
            dedup_key="test3",
            is_valid=False
        )
    ]
    db.add_all(businesses)
    db.commit()
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def mock_google_creds():
    creds_dict = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "123",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMOCK\n-----END PRIVATE KEY-----\n",
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "123",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test"
    }
    encoded = base64.b64encode(json.dumps(creds_dict).encode('utf-8')).decode('utf-8')
    os.environ["GOOGLE_CREDENTIALS_BASE64"] = encoded
    yield
    del os.environ["GOOGLE_CREDENTIALS_BASE64"]

@pytest.fixture
def empty_creds():
    if "GOOGLE_CREDENTIALS_BASE64" in os.environ:
        del os.environ["GOOGLE_CREDENTIALS_BASE64"]

@patch("src.services.google_sheets.gspread.authorize")
@patch("src.services.google_sheets.Credentials.from_service_account_info")
def test_missing_credentials(mock_creds, mock_gspread, empty_creds, setup_db):
    response = client.post("/api/v1/export/google-sheets", json={"export_all": True})
    assert response.status_code == 500
    assert "GOOGLE_CREDENTIALS_BASE64 environment variable is not set" in response.json()["detail"]

@patch("src.services.google_sheets.gspread.authorize")
@patch("src.services.google_sheets.Credentials.from_service_account_info")
def test_valid_export_all(mock_creds, mock_gspread, mock_google_creds, setup_db):
    # Setup mock sheet
    mock_client = MagicMock()
    mock_gspread.return_value = mock_client
    mock_sheet = MagicMock()
    mock_sheet.id = "mock_spreadsheet_id"
    mock_sheet.url = "https://docs.google.com/spreadsheets/d/mock_spreadsheet_id"
    mock_client.create.return_value = mock_sheet
    
    mock_worksheet = MagicMock()
    mock_sheet.sheet1 = mock_worksheet

    response = client.post("/api/v1/export/google-sheets", json={"export_all": True})
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["spreadsheet_id"] == "mock_spreadsheet_id"
    assert data["spreadsheet_url"] == "https://docs.google.com/spreadsheets/d/mock_spreadsheet_id"
    assert data["rows_exported"] == 3
    
    # Assert formatting
    mock_worksheet.format.assert_called_once()
    mock_worksheet.freeze.assert_called_with(rows=1)
    
    # Assert NO public sharing
    mock_sheet.share.assert_not_called()
    
    # Assert phone number has no artificial apostrophe
    # batch list contains the row data
    # We check the arguments passed to append_rows
    call_args = mock_worksheet.append_rows.call_args[0][0]
    # Check all rows in the batch
    phones = [row[2] for row in call_args]
    assert "+919876543210" in phones
    assert "011-23456789" in phones
    for p in phones:
        if p:
            assert not p.startswith("'")

@patch("src.services.google_sheets.gspread.authorize")
@patch("src.services.google_sheets.Credentials.from_service_account_info")
def test_filter_export(mock_creds, mock_gspread, mock_google_creds, setup_db):
    mock_client = MagicMock()
    mock_gspread.return_value = mock_client
    mock_sheet = MagicMock()
    mock_client.create.return_value = mock_sheet
    mock_worksheet = MagicMock()
    mock_sheet.sheet1 = mock_worksheet

    # Filter for is_valid=True
    response = client.post("/api/v1/export/google-sheets", json={
        "filters": {"is_valid": True},
        "export_all": False
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["rows_exported"] == 2

@patch("src.services.google_sheets.gspread.authorize")
@patch("src.services.google_sheets.Credentials.from_service_account_info")
def test_empty_export(mock_creds, mock_gspread, mock_google_creds, setup_db):
    mock_client = MagicMock()
    mock_gspread.return_value = mock_client
    mock_sheet = MagicMock()
    mock_client.create.return_value = mock_sheet
    mock_worksheet = MagicMock()
    mock_sheet.sheet1 = mock_worksheet

    # Filter for non-existent category
    response = client.post("/api/v1/export/google-sheets", json={
        "filters": {"category": "SpaceStation"},
        "export_all": False
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["rows_exported"] == 0
    # Headers should still be written
    assert mock_worksheet.append_row.called
    
@patch("src.services.google_sheets.gspread.authorize")
@patch("src.services.google_sheets.Credentials.from_service_account_info")
def test_google_api_failure(mock_creds, mock_gspread, mock_google_creds, setup_db):
    mock_client = MagicMock()
    mock_gspread.return_value = mock_client
    # Simulate API failure during creation
    mock_client.create.side_effect = Exception("Google API Quota Exceeded")
    
    response = client.post("/api/v1/export/google-sheets", json={"export_all": True})
    
    assert response.status_code == 500
    assert "Google API Quota Exceeded" in response.json()["detail"]

@patch("src.services.google_sheets.gspread.authorize")
@patch("src.services.google_sheets.Credentials.from_service_account_info")
def test_selected_ids_export(mock_creds, mock_gspread, mock_google_creds, setup_db):
    mock_client = MagicMock()
    mock_gspread.return_value = mock_client
    mock_sheet = MagicMock()
    mock_client.create.return_value = mock_sheet
    mock_worksheet = MagicMock()
    mock_sheet.sheet1 = mock_worksheet

    # We need to know a valid ID to test properly, let's fetch one from DB
    with TestingSessionLocal() as db:
        biz = db.query(Business).first()
        valid_id = biz.business_id

    response = client.post("/api/v1/export/google-sheets", json={
        "selected_ids": [valid_id],
        "export_all": False
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["rows_exported"] == 1
