import os
import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from src.main import app
from src.database import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base
from src.models import Location, Category, Job, Business, RunLog, WhatsAppAccount, WhatsAppTemplate, WhatsAppCampaign, WhatsAppCampaignRecipient, WhatsAppCampaignLog

from sqlalchemy.pool import StaticPool

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_connect_account_success():
    with patch.dict(os.environ, {
        "MOCK_WHATSAPP_API": "true",
        "META_ACCESS_TOKEN": "test_token",
        "META_PHONE_NUMBER_ID": "12345"
    }):
        response = client.post("/api/v1/whatsapp/accounts/connect")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Connected"
        assert data["phone_number_id"] == "12345"
        assert data["display_name"] == "Mock Business Account"
        assert data["phone_number"] == "+1 555-0198"

def test_connect_account_missing_config():
    with patch.dict(os.environ, {
        "MOCK_WHATSAPP_API": "false",
    }, clear=True):
        response = client.post("/api/v1/whatsapp/accounts/connect")
        assert response.status_code == 400
        assert "WhatsApp Meta credentials are not configured" in response.json()["detail"]

def test_connect_account_failed_verification():
    with patch.dict(os.environ, {
        "MOCK_WHATSAPP_API": "false",
        "META_ACCESS_TOKEN": "invalid_token",
        "META_PHONE_NUMBER_ID": "12345"
    }):
        with patch('requests.get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.json.return_value = {"error": {"message": "Invalid OAuth access token"}}
            mock_get.return_value = mock_resp
            
            response = client.post("/api/v1/whatsapp/accounts/connect")
            assert response.status_code == 400
            assert "Invalid OAuth access token" in response.json()["detail"]
