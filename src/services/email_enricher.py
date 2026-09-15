import asyncio
import re
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse
from src.utils.logging import logger

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

class EmailEnricher:
    def __init__(
        self,
        max_pages_per_site: int = 4,
        navigation_timeout_ms: int = 15000,
        max_concurrency: int = 5
    ):
        self.max_pages_per_site = max_pages_per_site
        self.navigation_timeout_ms = navigation_timeout_ms
        self.max_concurrency = max_concurrency

    def enrich_batch(self, businesses: List[Dict]) -> List[Dict]:
        """
        Takes a list of business dicts with at minimum: business_id, name, website.
        Returns a list of dicts with business_id and the enriched fields:
        email, email_source_url, email_enrichment_status
        """
        if not businesses:
            return []
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Cannot use asyncio.run() if event loop is already running
                import nest_asyncio
                nest_asyncio.apply()
        except RuntimeError:
            pass

        return asyncio.run(self._enrich_batch_async(businesses))

    async def _enrich_batch_async(self, businesses: List[Dict]) -> List[Dict]:
        from playwright.async_api import async_playwright
        
        results = []
        semaphore = asyncio.Semaphore(self.max_concurrency)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            tasks = []
            for biz in businesses:
                tasks.append(self._process_business(context, biz, semaphore))
                
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            await context.close()
            await browser.close()
            
        # Clean up results (handle exceptions from gather)
        final_results = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"Error enriching {businesses[i].get('name')}: {res}")
                final_results.append({
                    "business_id": businesses[i]["business_id"],
                    "email": None,
                    "email_source_url": None,
                    "email_enrichment_status": "error"
                })
            else:
                final_results.append(res)
                
        return final_results

    async def _process_business(self, context, biz: Dict, semaphore: asyncio.Semaphore) -> Dict:
        async with semaphore:
            return await self._enrich_single_website(context, biz)

    async def _enrich_single_website(self, context, biz: Dict) -> Dict:
        business_id = biz["business_id"]
        website = biz.get("website")
        name = biz.get("name", "Unknown")

        if not website:
            return {
                "business_id": business_id,
                "email": None,
                "email_source_url": None,
                "email_enrichment_status": "no_website"
            }
            
        website = website.strip()
        if not website.startswith('http'):
            website = 'https://' + website

        parsed_url = urlparse(website)
        base_domain = parsed_url.netloc.lower()
        if base_domain.startswith('www.'):
            base_domain = base_domain[4:]

        logger.info(f"Enriching email for {name} at {website}")
        
        page = await context.new_page()
        visited: Set[str] = set()
        to_visit = [website]
        found_emails = set()
        email_source = None
        status = "not_found"

        try:
            pages_visited = 0
            while to_visit and pages_visited < self.max_pages_per_site:
                current_url = to_visit.pop(0)
                if current_url in visited:
                    continue
                    
                visited.add(current_url)
                pages_visited += 1
                
                try:
                    response = await page.goto(current_url, timeout=self.navigation_timeout_ms, wait_until="domcontentloaded")
                    if response and response.status in [403, 401, 429]:
                        if pages_visited == 1:
                            status = "blocked"
                            break
                        else:
                            continue
                    
                    # Bounded wait for JavaScript-rendered content
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    logger.debug(f"Failed to navigate to {current_url}: {e}")
                    if pages_visited == 1:
                        status = "timeout"
                        break
                    continue
                
                # Check for blocking/captcha on page content
                page_text = await page.evaluate("document.body.innerText")
                if "captcha" in page_text.lower() and ("verify you are human" in page_text.lower() or "security check" in page_text.lower()):
                    if pages_visited == 1:
                        status = "blocked"
                        break
                    continue

                # Extract emails from mailto and text
                page_emails = self._extract_emails_from_text(page_text)
                
                # Check mailto links
                try:
                    hrefs = await page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('a[href^="mailto:"]')).map(a => a.href);
                    }""")
                    for href in hrefs:
                        email = href.replace('mailto:', '').split('?')[0].strip()
                        if self._is_valid_email(email):
                            page_emails.add(email.lower())
                except Exception:
                    pass
                
                # Extract emails from rendered HTML source
                try:
                    html_content = await page.content()
                    html_emails = self._extract_emails_from_text(html_content)
                    page_emails.update(html_emails)
                except Exception:
                    pass
                
                if page_emails:
                    found_emails.update(page_emails)
                    email_source = current_url
                    status = "found"
                    break # Stop at first page we find an email
                
                # If homepage, find internal links to contact/about
                if pages_visited == 1:
                    try:
                        links = await page.evaluate("""() => {
                            return Array.from(document.querySelectorAll('a')).map(a => a.href);
                        }""")
                        
                        contact_links = []
                        for link in links:
                            if not link or not link.startswith('http'):
                                continue
                            link_parsed = urlparse(link)
                            link_domain = link_parsed.netloc.lower()
                            if link_domain.startswith('www.'):
                                link_domain = link_domain[4:]
                                
                            if link_domain != base_domain:
                                continue
                                
                            path_and_fragment = (link_parsed.path + link_parsed.fragment).lower()
                            if any(k in path_and_fragment for k in ['contact', 'about']):
                                contact_links.append(link)
                                
                        # Add unique contact links to visit queue
                        for link in set(contact_links):
                            if link not in visited and link not in to_visit:
                                to_visit.append(link)
                    except Exception:
                        pass
                        
        finally:
            await page.close()

        best_email = self._select_best_email(found_emails)
        if best_email:
            return {
                "business_id": business_id,
                "email": best_email,
                "email_source_url": email_source,
                "email_enrichment_status": "found"
            }
        else:
            return {
                "business_id": business_id,
                "email": None,
                "email_source_url": None,
                "email_enrichment_status": status
            }

    def _extract_emails_from_text(self, text: str) -> Set[str]:
        if not text:
            return set()
        emails = set()
        matches = EMAIL_REGEX.findall(text)
        for match in matches:
            match = match.strip().lower()
            if self._is_valid_email(match):
                emails.add(match)
        return emails
        
    def _is_valid_email(self, email: str) -> bool:
        email = email.lower()
        if email.endswith(('.png', '.jpg', '.jpeg', '.gif', '.css', '.js')):
            return False
        if email.startswith(('sentry@', 'example@', 'email@', 'yourname@', 'test@')):
            return False
        return True

    def _select_best_email(self, emails: Set[str]) -> Optional[str]:
        if not emails:
            return None
            
        emails_list = list(emails)
        # Prefer info, contact, sales, support, hello, office, admin
        preferred_prefixes = ['info@', 'contact@', 'sales@', 'support@', 'hello@', 'office@', 'admin@']
        
        for email in emails_list:
            for prefix in preferred_prefixes:
                if email.startswith(prefix):
                    return email
                    
        return emails_list[0]

email_enricher = EmailEnricher()
