import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.email_enricher import EmailEnricher

@pytest.mark.anyio
async def test_domain_equivalence_and_fragments():
    enricher = EmailEnricher(max_pages_per_site=10)
    
    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page
    
    # Simulate a successful page load
    mock_response = MagicMock()
    mock_response.status = 200
    mock_page.goto.return_value = mock_response
    
    # We will control the evaluate return values based on the argument
    async def mock_evaluate(script):
        if "innerText" in script:
            return "Some text"
        elif "mailto" in script:
            return []
        elif "querySelectorAll('a')" in script:
            # First visit to base url returns these links
            return [
                "https://www.example.com/contact", # Should be visited (www equivalence)
                "https://malicious-example.com/contact", # Should NOT be visited (different domain)
                "https://example.com/#contact", # Should be visited (fragment contact)
                "https://example.com/#/contact-us", # Should be visited
                "https://example.com/#about", # Should be visited
                "https://example.com/#products", # Should NOT be visited (non-contact fragment)
                "https://www.example.com/#about" # Should be visited
            ]
        return None
        
    mock_page.evaluate.side_effect = mock_evaluate
    
    # Run the enrichment
    biz = {"business_id": "1", "name": "Test", "website": "https://example.com"}
    result = await enricher._enrich_single_website(mock_context, biz)
    
    # Now check what URLs were passed to page.goto
    # call_args_list contains the arguments passed to page.goto
    urls_visited = [call.args[0] for call in mock_page.goto.call_args_list]
    
    # The first URL visited should be the base URL
    assert "https://example.com" in urls_visited
    
    # Allowed links
    assert "https://www.example.com/contact" in urls_visited
    assert "https://example.com/#contact" in urls_visited
    assert "https://example.com/#/contact-us" in urls_visited
    assert "https://example.com/#about" in urls_visited
    assert "https://www.example.com/#about" in urls_visited
    
    # Rejected links
    assert "https://malicious-example.com/contact" not in urls_visited
    assert "https://example.com/#products" not in urls_visited
