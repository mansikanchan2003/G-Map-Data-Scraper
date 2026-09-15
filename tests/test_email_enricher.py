import pytest
from unittest.mock import MagicMock, patch
from src.services.email_enricher import EmailEnricher

def test_extract_emails_from_text():
    enricher = EmailEnricher()
    # 2. visible email extraction
    text = "Contact us at info@example.com or support@example.com."
    emails = enricher._extract_emails_from_text(text)
    assert "info@example.com" in emails
    assert "support@example.com" in emails

    # 4. email normalization and 5. duplicate email removal
    text2 = "Email us at INFO@EXAMPLE.COM. Yes, info@example.com."
    emails2 = enricher._extract_emails_from_text(text2)
    assert len(emails2) == 1
    assert "info@example.com" in emails2

def test_is_valid_email():
    enricher = EmailEnricher()
    assert enricher._is_valid_email("test@example.png") == False
    assert enricher._is_valid_email("sentry@example.com") == False
    assert enricher._is_valid_email("sales@realcompany.com") == True

def test_select_best_email():
    enricher = EmailEnricher()
    emails = {"personal@gmail.com", "info@company.com", "sales@company.com"}
    best = enricher._select_best_email(emails)
    assert best in ["info@company.com", "sales@company.com"] # Info or sales is preferred

    emails2 = {"ceo@company.com"}
    assert enricher._select_best_email(emails2) == "ceo@company.com"

# Using pytest-asyncio to test some async logic, but we can just mock enrich_batch directly
@patch("src.services.email_enricher.EmailEnricher._enrich_batch_async")
def test_enrich_batch_mocked(mock_async, monkeypatch):
    enricher = EmailEnricher()
    mock_async.return_value = [{"business_id": "1", "email": "info@test.com", "email_enrichment_status": "found"}]
    
    res = enricher.enrich_batch([{"business_id": "1", "name": "Test", "website": "http://test.com"}])
    assert len(res) == 1
    assert res[0]["email"] == "info@test.com"

