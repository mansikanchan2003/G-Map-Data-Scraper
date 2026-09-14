import time
import urllib.parse
from typing import Dict, Any, List, Optional
from src.utils.logging import logger
from src.services.geo_validator import extract_coords_from_url
from src.services.deduplicator import extract_place_id

class Selectors:
    # Google Maps Search result feed
    FEED = 'div[role="feed"]'
    LISTING_ITEM = 'div.Nv2PK, div[role="article"]'
    TITLE_LINK = 'a.hfpxzc'
    TITLE_TEXT = 'div.qBF1Pd'
    
    # Detail elements on single place view or detail page
    PHONE_BUTTON = 'button[data-item-id^="phone:tel:"], button[aria-label^="Phone"], button[aria-label*="Phone"]'
    ADDRESS_BUTTON = 'button[data-item-id="address"], button[aria-label*="Address"]'
    WEBSITE_LINK = 'a[data-item-id="authority"], a[aria-label^="Open website"], a[aria-label*="website"]'
    
    # Cookie consent / Interstitials
    CONSENT_BUTTON = 'button:has-text("Accept all"), button:has-text("I agree"), form[action*="consent"] button'
    
    # Blocking / CAPTCHA
    CAPTCHA = '#captcha-form, iframe[src*="recaptcha"], div.g-recaptcha, form#captcha'
    
    # Zero results
    NO_RESULTS = 'div:has-text("Google Maps can\'t find"), div:has-text("No results found")'

def build_search_url(category: str, pincode: Optional[str], latitude: float, longitude: float) -> str:
    """
    Constructs Google Maps search URL combining semantic query and geographic coordinates.
    """
    clean_pincode = str(pincode).strip() if pincode and str(pincode).strip() != "NOT FOUND" else ""
    if clean_pincode:
        search_term = f"{category} near {clean_pincode}"
    else:
        search_term = category
        
    encoded_query = urllib.parse.quote(search_term)
    return f"https://www.google.com/maps/search/{encoded_query}/@{latitude},{longitude},12z"

class GoogleMapsDiscoveryEngine:
    def __init__(
        self,
        headless: bool = True,
        navigation_timeout_ms: int = 30000,
        element_timeout_ms: int = 6000,
        delay_between_listings: float = 1.0,
        max_scroll_attempts: int = 4
    ):
        self.headless = headless
        self.navigation_timeout_ms = navigation_timeout_ms
        self.element_timeout_ms = element_timeout_ms
        self.delay_between_listings = delay_between_listings
        self.max_scroll_attempts = max_scroll_attempts
        self._playwright = None
        self._browser = None

    def _ensure_browser(self):
        if not self._playwright:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ]
            )

    def close(self):
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def execute_discovery(self, job_data: Dict[str, Any], page_override = None) -> Dict[str, Any]:
        """
        Execute discovery for a single job payload.
        job_data: {
            "job_id": str,
            "category": str,
            "pincode": Optional[str],
            "latitude": float,
            "longitude": float,
            "radius_km": Optional[float]
        }
        page_override: Optional mocked or external Playwright Page object for testability.
        """
        job_id = job_data.get("job_id", "unknown")
        category = job_data.get("category")
        latitude = job_data.get("latitude")
        longitude = job_data.get("longitude")
        pincode = job_data.get("pincode")

        # 1. Validation of input parameters
        if not category or not str(category).strip():
            return {
                "status": "failed",
                "job_id": job_id,
                "query": "",
                "count": 0,
                "results": [],
                "error": "Missing or invalid category"
            }

        if latitude is None or longitude is None:
            return {
                "status": "failed",
                "job_id": job_id,
                "query": "",
                "count": 0,
                "results": [],
                "error": "Missing coordinates (latitude/longitude)"
            }

        try:
            lat = float(latitude)
            lng = float(longitude)
        except (ValueError, TypeError):
            return {
                "status": "failed",
                "job_id": job_id,
                "query": "",
                "count": 0,
                "results": [],
                "error": f"Invalid coordinate format: lat={latitude}, lng={longitude}"
            }

        search_url = build_search_url(category, pincode, lat, lng)
        logger.info(f"Starting discovery for Job {job_id} | Query URL: {search_url}")

        context = None
        page = page_override
        should_close_page = False

        if page is None:
            self._ensure_browser()
            context = self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            should_close_page = True

        raw_results: List[Dict[str, Any]] = []
        partial_extraction_errors = 0

        try:
            # 2. Navigation
            try:
                page.goto(search_url, timeout=self.navigation_timeout_ms, wait_until="domcontentloaded")
            except Exception as nav_err:
                logger.error(f"Navigation failed for Job {job_id}: {nav_err}")
                return {
                    "status": "failed",
                    "job_id": job_id,
                    "query": search_url,
                    "count": 0,
                    "results": [],
                    "error": f"Navigation timeout or network failure: {str(nav_err)}"
                }

            # 3. Check for CAPTCHA / Bot detection
            if page.locator(Selectors.CAPTCHA).count() > 0:
                logger.warning(f"Blocking or CAPTCHA detected for Job {job_id}")
                return {
                    "status": "blocked",
                    "job_id": job_id,
                    "query": search_url,
                    "count": 0,
                    "results": [],
                    "error": "Google Maps access restricted or CAPTCHA presented",
                    "blocked_reason": "CAPTCHA_DETECTED"
                }

            # 4. Handle cookie consent dialog if displayed
            try:
                consent_btn = page.locator(Selectors.CONSENT_BUTTON).first
                if consent_btn.is_visible():
                    consent_btn.click(timeout=3000)
                    page.wait_for_timeout(1000)
            except Exception:
                pass

            # 5. Check for Zero Results
            page.wait_for_timeout(2000)
            if page.locator(Selectors.NO_RESULTS).count() > 0:
                logger.info(f"Zero results found for Job {job_id}")
                return {
                    "status": "zero_results",
                    "job_id": job_id,
                    "query": search_url,
                    "count": 0,
                    "results": [],
                    "error": None
                }

            # 6. Wait for listings container or direct listing card
            has_feed = False
            try:
                page.wait_for_selector(Selectors.FEED, timeout=self.element_timeout_ms)
                has_feed = True
            except Exception:
                # Might be a single direct result redirect or no feed
                pass

            # 7. Scroll Feed if multiple results
            if has_feed:
                feed_locator = page.locator(Selectors.FEED)
                previous_height = 0
                same_count = 0
                for _ in range(self.max_scroll_attempts):
                    try:
                        curr_height = feed_locator.evaluate("el => { el.scrollBy(0, 1000); return el.scrollTop; }")
                        if curr_height == previous_height:
                            same_count += 1
                        else:
                            same_count = 0
                        previous_height = curr_height
                        if same_count >= 2:
                            break
                        page.wait_for_timeout(1000)
                    except Exception:
                        break

            # 8. Identify listing elements
            listing_cards = page.locator(Selectors.LISTING_ITEM).all()
            logger.info(f"Discovered {len(listing_cards)} listing cards for Job {job_id}")

            if not listing_cards:
                # Check again if no results
                if page.locator(Selectors.NO_RESULTS).count() > 0:
                    return {
                        "status": "zero_results",
                        "job_id": job_id,
                        "query": search_url,
                        "count": 0,
                        "results": []
                    }
                return {
                    "status": "zero_results",
                    "job_id": job_id,
                    "query": search_url,
                    "count": 0,
                    "results": []
                }

            # 9. Extract listings (bounded and error-isolated)
            detail_page = context.new_page() if context else None
            
            for index, card in enumerate(listing_cards):
                try:
                    title_elem = card.locator(Selectors.TITLE_LINK).first
                    name = None
                    listing_url = None
                    
                    if title_elem.count() > 0:
                        name = title_elem.get_attribute("aria-label") or title_elem.inner_text()
                        listing_url = title_elem.get_attribute("href")
                    else:
                        title_fallback = card.locator(Selectors.TITLE_TEXT).first
                        if title_fallback.count() > 0:
                            name = title_fallback.inner_text()

                    if not name or not name.strip():
                        continue

                    name = name.strip()
                    phone = None
                    address = None
                    website = None
                    lat_ext, lng_ext = extract_coords_from_url(listing_url)
                    place_id = extract_place_id(listing_url)

                    # Extract detail page info if URL available
                    if listing_url and detail_page:
                        try:
                            detail_page.goto(listing_url, timeout=12000, wait_until="domcontentloaded")
                            page.wait_for_timeout(int(self.delay_between_listings * 1000))

                            # Phone
                            phone_btn = detail_page.locator(Selectors.PHONE_BUTTON).first
                            if phone_btn.count() > 0:
                                phone = phone_btn.inner_text() or phone_btn.get_attribute("aria-label")

                            # Address
                            addr_btn = detail_page.locator(Selectors.ADDRESS_BUTTON).first
                            if addr_btn.count() > 0:
                                address = addr_btn.get_attribute("aria-label") or addr_btn.inner_text()

                            # Website
                            web_link = detail_page.locator(Selectors.WEBSITE_LINK).first
                            if web_link.count() > 0:
                                website = web_link.get_attribute("href")

                            # Coordinate extraction from current URL after redirects
                            if not lat_ext or not lng_ext:
                                lat_ext, lng_ext = extract_coords_from_url(detail_page.url)
                            if not place_id:
                                place_id = extract_place_id(detail_page.url)

                        except Exception as detail_err:
                            logger.warning(f"Error fetching details for listing '{name}': {detail_err}")
                            partial_extraction_errors += 1

                    raw_results.append({
                        "name": name,
                        "address": address,
                        "phone": phone,
                        "website": website,
                        "google_maps_url": listing_url,
                        "place_id": place_id,
                        "latitude": lat_ext,
                        "longitude": lng_ext,
                        "category": category
                    })

                except Exception as listing_err:
                    logger.warning(f"Listing extraction error on card {index}: {listing_err}")
                    partial_extraction_errors += 1
                    continue

            if detail_page:
                try:
                    detail_page.close()
                except Exception:
                    pass

            status = "partial" if partial_extraction_errors > 0 and raw_results else "success"
            if not raw_results:
                status = "zero_results"

            return {
                "status": status,
                "job_id": job_id,
                "query": search_url,
                "count": len(raw_results),
                "results": raw_results,
                "error": None
            }

        except Exception as e:
            logger.error(f"Unexpected discovery error on Job {job_id}: {e}")
            return {
                "status": "failed",
                "job_id": job_id,
                "query": search_url,
                "count": 0,
                "results": [],
                "error": str(e)
            }
        finally:
            if should_close_page and page:
                try:
                    page.close()
                except Exception:
                    pass
            if context:
                try:
                    context.close()
                except Exception:
                    pass

# Singleton engine instance
discovery_engine = GoogleMapsDiscoveryEngine()
