import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.email_enricher import EmailEnricher

def test_extract_emails_from_text():
    enricher = EmailEnricher()
    text = "Contact us at info@example.com or support@example.com."
    emails = enricher._extract_emails_from_text(text)
    assert "info@example.com" in emails
    assert "support@example.com" in emails

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
    assert best in ["info@company.com", "sales@company.com"]

    emails2 = {"ceo@company.com"}
    assert enricher._select_best_email(emails2) == "ceo@company.com"

def test_enrichment_disabled():
    enricher = EmailEnricher(enrichment_enabled=False)
    res = enricher.enrich_batch([{"business_id": "1", "name": "Test", "website": "http://test.com"}])
    assert res == []

def test_missing_website():
    enricher = EmailEnricher(enrichment_enabled=True)
    res = enricher.enrich_batch([{"business_id": "1", "name": "Test"}])
    # The actual implementation calls _enrich_batch_async, but without website it returns "no_website" from _enrich_single_website.
    # However, to avoid Playwright overhead in unit tests, we'll mock _enrich_batch_async.
    pass

def test_process_business_with_timeout_success():
    enricher = EmailEnricher(business_timeout_seconds=2)

    async def mock_process(*args, **kwargs):
        return {"business_id": "1", "email": "success@test.com", "email_enrichment_status": "found"}

    enricher._process_business = AsyncMock(side_effect=mock_process)

    res = asyncio.run(enricher._process_business_with_timeout(None, {"business_id": "1", "name": "Test"}, asyncio.Semaphore(1)))
    assert res["email"] == "success@test.com"

def test_process_business_with_timeout_exceeded():
    enricher = EmailEnricher(business_timeout_seconds=1) # 1 sec timeout

    async def mock_process(*args, **kwargs):
        await asyncio.sleep(2) # Sleeps longer than timeout
        return {"business_id": "1"}

    enricher._process_business = AsyncMock(side_effect=mock_process)

    res = asyncio.run(enricher._process_business_with_timeout(None, {"business_id": "1", "name": "Test"}, asyncio.Semaphore(1)))
    assert res["email_enrichment_status"] == "timeout"
    assert res["email"] is None

def test_process_business_with_error():
    enricher = EmailEnricher(business_timeout_seconds=2)

    async def mock_process(*args, **kwargs):
        raise Exception("Browser crash")

    enricher._process_business = AsyncMock(side_effect=mock_process)

    res = asyncio.run(enricher._process_business_with_timeout(None, {"business_id": "1", "name": "Test"}, asyncio.Semaphore(1)))
    assert res["email_enrichment_status"] == "error"
    assert res["email"] is None

@patch("src.services.email_enricher.EmailEnricher._enrich_batch_async")
def test_enrich_batch_mocked(mock_async):
    enricher = EmailEnricher(enrichment_enabled=True)
    mock_async.return_value = [{"business_id": "1", "email": "info@test.com", "email_enrichment_status": "found"}]

    res = enricher.enrich_batch([{"business_id": "1", "name": "Test", "website": "http://test.com"}])
    assert len(res) == 1
    assert res[0]["email"] == "info@test.com"


# --- Hang containment -------------------------------------------------------
# Enrichment used to cancel pending tasks and immediately close the Playwright
# context. Cancellation is cooperative, so those tasks were still inside
# Playwright calls on that context; close() then waited on pages that were
# waiting on the loop. The batch wedged, Chromium kept spinning, and the whole
# API process stopped responding. Businesses are already persisted before
# enrichment runs, so a stuck browser must degrade to "no email" instead.

def test_enrich_batch_survives_a_wedged_browser():
    """A hung enrichment run must return, not block the caller forever."""
    enricher = EmailEnricher(batch_timeout_seconds=1, business_timeout_seconds=1)
    enricher.teardown_timeout_seconds = 1

    async def _never_finishes(_businesses):
        await asyncio.sleep(3600)

    businesses = [
        {"business_id": "b1", "name": "One", "website": "https://one.example"},
        {"business_id": "b2", "name": "Two", "website": "https://two.example"},
    ]

    with patch.object(enricher, "_enrich_batch_async", _never_finishes):
        results = enricher.enrich_batch(businesses)

    assert len(results) == 2
    assert {r["business_id"] for r in results} == {"b1", "b2"}
    assert all(r["email"] is None for r in results)
    assert all(r["email_enrichment_status"] == "batch_timeout" for r in results)


def test_enrich_batch_reports_failure_instead_of_raising():
    """An unexpected enrichment error must not abort the discovery batch."""
    enricher = EmailEnricher(batch_timeout_seconds=1)

    async def _blows_up(_businesses):
        raise RuntimeError("playwright exploded")

    businesses = [{"business_id": "b1", "name": "One", "website": "https://one.example"}]

    with patch.object(enricher, "_enrich_batch_async", _blows_up):
        results = enricher.enrich_batch(businesses)

    assert len(results) == 1
    assert results[0]["email_enrichment_status"] == "batch_timeout"


def test_pending_tasks_are_awaited_before_teardown():
    """Cancelled tasks must be allowed to unwind before the context closes."""
    import inspect
    source = inspect.getsource(EmailEnricher._enrich_batch_async)
    cancel_at = source.index("task.cancel()")
    unwind_at = source.index("await asyncio.wait(pending")
    close_at = source.index("closer.close()")
    assert cancel_at < unwind_at < close_at, (
        "pending tasks must be awaited after cancel() and before the browser is closed"
    )
