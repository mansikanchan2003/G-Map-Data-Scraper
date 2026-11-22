"""
The worker and scraper containers' entrypoint (Phase 1, 22 Nov 2026):

    APP_ROLE=worker  python -m src.worker
    APP_ROLE=scraper python -m src.worker

Starts this role's background threads (src.background) and keeps the process
alive. The database schema is the API's to set up (and the deploy's migrations),
so nothing here creates tables. A heartbeat file, touched every 30 seconds, lets
Docker's health check see the threads' process is alive.
"""
import logging
import os
import signal
import sys
import threading
import time

from src import background, roles
from src.utils.logging import setup_logging

logger = logging.getLogger("gmap_scraper")

HEARTBEAT = os.environ.get("WORKER_HEARTBEAT_FILE", "/tmp/autogmap_heartbeat")
BEAT_SECONDS = 30


def main() -> int:
    setup_logging()
    role = roles.role()
    if role not in ("worker", "scraper"):
        logger.error(f"worker event=WRONG_ROLE role={role}: set APP_ROLE to worker or scraper")
        return 2
    # The bot's taught phrasings, for anything here that matches what people write.
    try:
        from src.database import SessionLocal
        from src.services import faq_learning
        db = SessionLocal()
        try:
            faq_learning.load(db)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Could not load what the bot was taught: {e}")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    background.start()
    logger.info(f"worker event=READY role={role}")
    while not stop.is_set():
        try:
            with open(HEARTBEAT, "w") as f:
                f.write(str(int(time.time())))
        except OSError:
            pass
        stop.wait(BEAT_SECONDS)
    background.stop()
    logger.info(f"worker event=STOPPED role={role}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
