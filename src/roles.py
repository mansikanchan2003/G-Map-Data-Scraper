"""
Which parts of AutoGMap this process runs (Phase 1 of moving off one monolith, 22 Nov 2026).

One codebase, one image, three containers, chosen by APP_ROLE:

- api      The website, the WhatsApp webhook, the bot and the Inbox. Light, always up.
           Scraping it is asked for is queued (work_queue) for the scraper.
- worker   The background senders: nudges, follow-ups (with the journey sync and
           reports), call recordings, the Studio's photo queue.
- scraper  Google Maps in Chrome: the autopilot and the queued batches, behind its
           own memory limit, so a stuck browser stops scraping, never the website
           (19 Nov 2026: one did, for four hours).
- all      Everything in one process, as before: the default, for development,
           the tests and staging.

Each thread's own switch (DISCOVERY_AUTOPILOT_THREAD, BOT_NUDGE_THREAD, ...) still
turns it off within its role.
"""
import os

ROLES = ("all", "api", "worker", "scraper")

# What each role runs. "queue_scraping" means asking for a batch puts it in the work
# queue instead of running it here.
_PARTS = {
    "all": {"startup", "insights_cache", "autopilot", "scrape_queue", "memory_guard", "photo_queue",
            "nudges", "followups", "call_recordings"},
    "api": {"startup", "insights_cache", "queue_scraping"},
    "worker": {"photo_queue", "nudges", "followups", "call_recordings"},
    "scraper": {"autopilot", "scrape_queue", "memory_guard"},
}


def role() -> str:
    value = (os.environ.get("APP_ROLE") or "all").strip().lower()
    return value if value in ROLES else "all"


def runs(part: str) -> bool:
    """Whether this process runs `part` (a background thread or a startup task)."""
    return part in _PARTS[role()]


def queue_scraping() -> bool:
    """True where a scraping request is handed to the scraper container instead of run here."""
    return runs("queue_scraping")
