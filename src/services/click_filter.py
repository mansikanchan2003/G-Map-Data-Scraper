"""
Telling a person tapping a campaign link apart from a machine fetching it.

Every hit on /r/{token} used to count as a click. Of the first seven
recorded, six were curl, Python's urllib and headless Chrome — testing, but
indistinguishable in the counts from a recipient. Link-preview fetchers
(WhatsApp's own, Facebook's) and security scanners hit links the same way.

The judgement is made from what the request says about itself: its method
and its user agent. It deliberately errs towards "human": an unfamiliar
phone browser must never be thrown away, so only agents that name
themselves as tools, bots or preview fetchers are flagged. Flagged hits are
still recorded, with the reason, so the call can be checked and revised.
"""
import re
from typing import Optional

# (pattern, reason). Matched case-insensitively against the user agent.
_AUTOMATED_AGENTS = [
    # Link previews: the app building a card, not the person opening it.
    (r"\bWhatsApp/", "WhatsApp link preview"),
    (r"facebookexternalhit|Facebot|meta-external(agent|fetcher)", "Meta link preview"),
    (r"TelegramBot|Twitterbot|Slackbot|Discordbot|LinkedInBot|SkypeUriPreview|Pinterest", "link preview"),
    # Browsers driven by software.
    (r"HeadlessChrome|PhantomJS|Puppeteer|Playwright|Selenium|Lighthouse", "headless browser"),
    # Command-line and programming-language HTTP clients.
    (r"^curl/|^Wget/|python-requests|Python-urllib|python-httpx|aiohttp|^Go-http-client|"
     r"^Java/|Apache-HttpClient|node-fetch|axios/|^undici|PostmanRuntime|insomnia", "script or HTTP tool"),
    # Crawlers. Not a bare "bot": CUBOT phones put "CUBOT X30" in their agent.
    # Bots announce themselves as "(compatible; SomeBot/1.0; +http://...)",
    # and the contact URL is the tell.
    (r"\+https?://|compatible;[^)]*bot|Googlebot|bingbot|YandexBot|Baiduspider|DuckDuckBot|"
     r"Applebot|AhrefsBot|SemrushBot|PetalBot|Bytespider|crawler|spider", "bot or crawler"),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), reason) for p, reason in _AUTOMATED_AGENTS]


def automated_reason(user_agent: Optional[str], method: str = "GET") -> Optional[str]:
    """Why a hit is not a person, or None when it looks like one."""
    if (method or "GET").upper() == "HEAD":
        # A HEAD asks whether the link works without opening it: scanners and
        # preview checkers. A person tapping a link always sends a GET. The
        # route currently refuses HEAD (405) before recording anything; this
        # holds if that ever changes.
        return "HEAD request (link checker)"
    ua = (user_agent or "").strip()
    if not ua:
        # Every real browser sends one.
        return "no user agent"
    for pattern, reason in _COMPILED:
        if pattern.search(ua):
            return reason
    return None
