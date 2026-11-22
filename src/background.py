"""
The background threads, started by whichever process runs them (src.roles).

The API starts its share from its lifespan (src.main); the worker and the scraper
containers run nothing else (src.worker). Off under pytest, where a background
thread would race the tests' own databases. Each thread's own switch still turns it
off within its role.
"""
import logging
import os
import sys

from src import roles

logger = logging.getLogger("gmap_scraper")


def _switch(name: str) -> bool:
    return os.environ.get(name, "true").lower() == "true"


def start() -> None:
    if "pytest" in sys.modules:
        return
    # Kills the scraper's browsers before they fill the container's memory
    # and stall the whole app (see browser_processes).
    if roles.runs("memory_guard"):
        from src.utils import browser_processes
        browser_processes.start_memory_guard()
    # The scraping autopilot. It idles until switched on from the dashboard.
    if roles.runs("autopilot") and _switch("DISCOVERY_AUTOPILOT_THREAD"):
        from src.services import discovery_autopilot
        discovery_autopilot.start()
    # Batches and single jobs the API queued for the scraper (work_queue).
    if roles.runs("scrape_queue") and roles.role() != "all":
        from src.services import work_queue
        work_queue.start()
    # Finishes Studio drafts waiting for the free image allowance to return.
    if roles.runs("photo_queue") and _switch("STUDIO_PHOTO_QUEUE_THREAD"):
        from src.services import photo_queue
        photo_queue.start()
    # Reminds people who stopped answering the bot, an hour on.
    if roles.runs("nudges") and _switch("BOT_NUDGE_THREAD"):
        from src.services import nudges
        nudges.start()
    # Carries out what each disposition calls for: nudges, callbacks, next-day retries.
    if roles.runs("followups") and _switch("FOLLOWUP_THREAD"):
        from src.services import followups
        followups.start()
    # Fetches new call recordings from the call-recorder app, when its endpoint is set.
    if roles.runs("call_recordings") and _switch("CALL_RECORDINGS_THREAD"):
        from src.services import call_recordings
        call_recordings.start()
    # Campaign Insights' slow parts, worked out ahead (insights_cache, 19 Nov 2026).
    # In the API: the answers are kept in its memory.
    if roles.runs("insights_cache"):
        from src.services import insights_cache
        insights_cache.start()
    logger.info(f"background event=STARTED role={roles.role()}")


def stop() -> None:
    try:
        from src.services import (call_recordings, discovery_autopilot, followups, nudges, photo_queue,
                                  work_queue)
        for part in (discovery_autopilot, work_queue, photo_queue, nudges, followups, call_recordings):
            part.stop()
    except Exception:
        pass
