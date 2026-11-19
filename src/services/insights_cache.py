"""
Campaign Insights, ready before anyone asks (19 Nov 2026): the page took 4-6 seconds a part
(the plan 6.2 s, the campaign list 3.9 s, the playbook 3.3 s on the server), while Kiosk KAI's
card came at once.

Each part is kept in memory with the time it was worked out, and served from there. A part
older than FRESH_SECONDS is still served at once, and worked out again in the background;
a thread also keeps every part warm, so the first person after a quiet spell waits too
little. Only the very first request after a restart waits for the work.

INSIGHTS_CACHE_SECONDS=0 turns the keeping off (the tests do): every request works it out.
"""
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("gmap_scraper.insights_cache")

_parts: Dict[str, Callable] = {}
_kept: Dict[str, tuple] = {}          # key -> (worked out at, value)
_busy: Dict[str, threading.Lock] = {}
_thread: Optional[threading.Thread] = None


def fresh_seconds() -> float:
    return float(os.environ.get("INSIGHTS_CACHE_SECONDS", "300"))


def register(key: str, compute: Callable) -> None:
    """compute(db) works the part out with a session of its own."""
    _parts[key] = compute
    _busy.setdefault(key, threading.Lock())


def _work(key: str, db=None) -> Any:
    from src.database import SessionLocal
    own = db is None
    db = SessionLocal() if own else db
    try:
        started = time.monotonic()
        value = _parts[key](db)
        _kept[key] = (time.monotonic(), value)
        logger.info(f"insights_cache event=REFRESHED part={key} seconds={round(time.monotonic() - started, 1)}")
        return value
    finally:
        if own:
            db.close()


def _refresh_in_background(key: str) -> None:
    lock = _busy[key]
    if not lock.acquire(blocking=False):
        return

    def run():
        try:
            _work(key)
        except Exception:
            logger.exception(f"insights_cache event=REFRESH_FAILED part={key}")
        finally:
            lock.release()
    threading.Thread(target=run, daemon=True, name=f"insights-{key}").start()


def get(key: str, db) -> Any:
    """The part, at once when one is kept; worked out now (with the request's session) when none is."""
    ttl = fresh_seconds()
    if ttl <= 0:
        return _parts[key](db)
    kept = _kept.get(key)
    if kept is None:
        with _busy[key]:
            kept = _kept.get(key)
            if kept is None:
                return _work(key, db)
    if time.monotonic() - kept[0] > ttl:
        _refresh_in_background(key)
    return kept[1]


def forget(key: Optional[str] = None) -> None:
    """Drop what is kept (all of it, or one part), e.g. after a campaign is launched."""
    if key:
        _kept.pop(key, None)
    else:
        _kept.clear()


def _loop() -> None:
    while True:
        for key in list(_parts):
            lock = _busy[key]
            if lock.acquire(blocking=False):
                try:
                    _work(key)
                except Exception:
                    logger.exception(f"insights_cache event=WARM_FAILED part={key}")
                finally:
                    lock.release()
        time.sleep(max(fresh_seconds() * 0.8, 60))


def start() -> None:
    """Keep every part warm from the start (not when keeping is off)."""
    global _thread
    if fresh_seconds() <= 0 or (_thread and _thread.is_alive()):
        return
    _thread = threading.Thread(target=_loop, daemon=True, name="insights-warm")
    _thread.start()
