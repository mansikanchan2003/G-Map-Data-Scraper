import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.email_enricher import EmailEnricher

@pytest.mark.anyio
async def test_html_extraction_only():
    enricher = EmailEnricher(max_pages_per_site=1)
    
    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page
    
    mock_response = MagicMock()
    mock_response.status = 200
    mock_page.goto.return_value = mock_response
    
    async def mock_evaluate(script):
        if "innerText" in script:
            return "No email here visually."
        elif "mailto" in script:
            return []
        elif "querySelectorAll('a')" in script:
            return []
        return None
        
    mock_page.evaluate.side_effect = mock_evaluate
    # Email exists in HTML source (e.g. meta tag)
    mock_page.content.return_value = '<html><head><meta property="og:email" content="hidden@company.com"></head><body>No email here visually.</body></html>'
    
    biz = {"business_id": "1", "name": "Test", "website": "https://example.com"}
    result = await enricher._enrich_single_website(mock_context, biz)
    
    assert result["email"] == "hidden@company.com"
    assert result["email_source_url"] == "https://example.com"
    assert result["email_enrichment_status"] == "found"

@pytest.mark.anyio
async def test_html_extraction_deduplication():
    enricher = EmailEnricher(max_pages_per_site=1)
    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page
    
    mock_page.goto.return_value = MagicMock(status=200)
    
    async def mock_evaluate(script):
        if "innerText" in script:
            return "Contact: info@company.com"
        elif "mailto" in script:
            return ["mailto:info@company.com"]
        return []
        
    mock_page.evaluate.side_effect = mock_evaluate
    # HTML has the exact same email
    mock_page.content.return_value = '<html><body>Contact: <a href="mailto:info@company.com">info@company.com</a></body></html>'
    
    biz = {"business_id": "1", "name": "Test", "website": "https://example.com"}
    result = await enricher._enrich_single_website(mock_context, biz)
    
    assert result["email"] == "info@company.com"
    
@pytest.mark.anyio
async def test_html_extraction_deterministic_selection():
    enricher = EmailEnricher(max_pages_per_site=1)
    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page
    
    mock_page.goto.return_value = MagicMock(status=200)
    
    async def mock_evaluate(script):
        if "innerText" in script:
            return ""
        elif "mailto" in script:
            return []
        return []
        
    mock_page.evaluate.side_effect = mock_evaluate
    # HTML has multiple emails. Sales/Info is preferred over personal
    mock_page.content.return_value = '<!-- john@company.com sales@company.com -->'
    
    biz = {"business_id": "1", "name": "Test", "website": "https://example.com"}
    result = await enricher._enrich_single_website(mock_context, biz)
    
    assert result["email"] == "sales@company.com"

@pytest.mark.anyio
async def test_html_extraction_junk_filtering():
    enricher = EmailEnricher(max_pages_per_site=1)
    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page
    
    mock_page.goto.return_value = MagicMock(status=200)
    
    async def mock_evaluate(script):
        if "innerText" in script:
            return ""
        elif "mailto" in script:
            return []
        return []
        
    mock_page.evaluate.side_effect = mock_evaluate
    # HTML has fake, test, png emails
    mock_page.content.return_value = '<img src="logo@2x.png" /> sentry@domain.com example@domain.com'
    
    biz = {"business_id": "1", "name": "Test", "website": "https://example.com"}
    result = await enricher._enrich_single_website(mock_context, biz)
    
    assert result["email"] is None

@pytest.mark.anyio
async def test_html_extraction_js_string_false_positive():
    enricher = EmailEnricher(max_pages_per_site=1)
    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page
    
    mock_page.goto.return_value = MagicMock(status=200)
    
    async def mock_evaluate(script):
        if "innerText" in script:
            return ""
        elif "mailto" in script:
            return []
        return []
        
    mock_page.evaluate.side_effect = mock_evaluate
    # JS string looking like email but isn't valid context or is a test string
    mock_page.content.return_value = '<script>const email = "test@example.com";</script>'
    
    biz = {"business_id": "1", "name": "Test", "website": "https://example.com"}
    result = await enricher._enrich_single_website(mock_context, biz)
    
    assert result["email"] is None
