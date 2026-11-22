"""
System health: whether the website, the worker and the scraper are alive, for the
Dashboard (22 Nov 2026), so nobody has to open the server to find out.

Each process (src.roles) writes a heartbeat into app_settings every 30 seconds:
when, its threads and whether each is alive, its memory against its container's
limit, and its last errors in plain words. The API reads them all, with the work
queue and the last scraping run, and says per part: Running, Needs a look, or
Stopped.
"""
import json
import logging
import os
import socket
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src import roles

logger = logging.getLogger("gmap_scraper.system_health")

KEY = "system_health:"
BEAT_SECONDS = 30
# A heartbeat older than this means the part is not answering.
STALE_SECONDS = 150
# Errors this recent count against a part's health.
ERROR_WINDOW_SECONDS = 3600
MAX_ERRORS = 15

LABELS = {
    "api": "Website",
    "worker": "Worker",
    "scraper": "Scraper",
    "all": "AutoGMap",
}
JOBS = {
    "api": "The website, WhatsApp webhook, bot and Inbox",
    "worker": "Reminders, follow-ups, call recordings, Studio photos",
    "scraper": "Google Maps scraping: the autopilot and queued batches",
    "all": "Everything, in one process",
}
# The background threads each part runs, by the module that holds them.
THREADS = {
    "autopilot": ("discovery_autopilot", "Scraping autopilot"),
    "scrape_queue": ("work_queue", "Scraping queue"),
    "photo_queue": ("photo_queue", "Studio photo queue"),
    "nudges": ("nudges", "Bot reminders"),
    "followups": ("followups", "Follow-ups"),
    "call_recordings": ("call_recordings", "Call recordings"),
    "insights_cache": ("insights_cache", "Insights cache"),
}

_started_at = datetime.now(timezone.utc)
_errors: deque = deque(maxlen=MAX_ERRORS)


class _ErrorBuffer(logging.Handler):
    """Keeps this process's last errors, one line each, for its heartbeat."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = record.getMessage().splitlines()[0][:300] if record.getMessage() else ""
            _errors.append({"at": datetime.now(timezone.utc).isoformat(), "where": record.name[:60], "text": text})
        except Exception:
            pass


def _threads() -> List[dict]:
    import importlib
    out = []
    for part, (module, label) in THREADS.items():
        if not roles.runs(part) or (part == "scrape_queue" and roles.role() == "all"):
            continue
        try:
            thread = getattr(importlib.import_module(f"src.services.{module}"), "_thread", None)
        except Exception:
            thread = None
        out.append({"name": part, "label": label, "alive": bool(thread and thread.is_alive())})
    return out


def snapshot() -> dict:
    from src.utils import browser_processes
    used, limit = browser_processes._cgroup_memory()
    return {
        "role": roles.role(), "host": socket.gethostname()[:60], "pid": os.getpid(),
        "started_at": _started_at.isoformat(), "at": datetime.now(timezone.utc).isoformat(),
        "memory": {"used_mb": used >> 20, "limit_mb": limit >> 20} if limit else None,
        "threads": _threads(),
        "errors": list(_errors),
    }


def beat() -> None:
    from src.database import SessionLocal
    from src.models import AppSetting
    db = SessionLocal()
    try:
        key = KEY + roles.role()
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if row is None:
            row = AppSetting(key=key)
            db.add(row)
        row.value = json.dumps(snapshot())
        db.commit()
    finally:
        db.close()


_thread: Optional[threading.Thread] = None


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    logging.getLogger().addHandler(_buffer())

    def loop():
        while True:
            try:
                beat()
            except Exception:
                logger.warning("system_health event=BEAT_FAILED", exc_info=True)
            time.sleep(BEAT_SECONDS)

    _thread = threading.Thread(target=loop, name="system-health", daemon=True)
    _thread.start()


def _buffer() -> logging.Handler:
    handler = _ErrorBuffer(level=logging.ERROR)
    return handler


# --- The Dashboard's view --------------------------------------------------------------

def _age(iso: Optional[str], now: datetime) -> Optional[int]:
    try:
        d = datetime.fromisoformat(iso) if iso else None
    except ValueError:
        return None
    return int((now - d).total_seconds()) if d else None


def _iso(d: Optional[datetime]) -> Optional[str]:
    """A stored time as ISO with its zone; one stored without (SQLite) is UTC."""
    if d is None:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).isoformat()


def _part(role: str, beat_: Optional[dict], now: datetime, show_errors: bool) -> dict:
    if not beat_:
        return {"role": role, "label": LABELS[role], "job": JOBS[role], "status": "stopped",
                "why": "It has not reported yet. It may not have started.", "seen_seconds_ago": None,
                "threads": [], "errors": [], "memory": None, "up_since": None}
    seen = _age(beat_.get("at"), now)
    recent = [e for e in beat_.get("errors") or [] if (_age(e.get("at"), now) or 0) <= ERROR_WINDOW_SECONDS]
    dead = [t["label"] for t in beat_.get("threads") or [] if not t.get("alive")]
    mem = beat_.get("memory")
    high_memory = bool(mem and mem.get("limit_mb") and mem["used_mb"] >= 0.85 * mem["limit_mb"])
    if seen is None or seen > STALE_SECONDS:
        status, why = "stopped", f"No sign of life for {round((seen or 0) / 60)} minutes."
    elif dead:
        status, why = "warning", "Not running: " + ", ".join(dead) + "."
    elif high_memory:
        status, why = "warning", f"Memory nearly full ({mem['used_mb']} of {mem['limit_mb']} MB)."
    elif recent:
        status, why = "warning", f"{len(recent)} error{'s' if len(recent) != 1 else ''} in the last hour."
    else:
        status, why = "ok", "Running normally."
    return {"role": role, "label": LABELS[role], "job": JOBS[role], "status": status, "why": why,
            "seen_seconds_ago": seen, "up_since": beat_.get("started_at"), "memory": mem,
            "threads": beat_.get("threads") or [],
            "errors": list(reversed(recent))[:8] if show_errors else [], "error_count": len(recent)}


def report(db, show_errors: bool = True) -> dict:
    from src.models import AppSetting, RunLog
    from src.models.work_queue import QueuedTask
    now = datetime.now(timezone.utc)
    beats: Dict[str, dict] = {}
    for row in db.query(AppSetting).filter(AppSetting.key.like(KEY + "%")):
        try:
            beats[row.key[len(KEY):]] = json.loads(row.value or "{}")
        except ValueError:
            continue
    # This process's own state, fresh rather than up to 30 seconds old.
    beats[roles.role()] = snapshot()
    split = roles.role() != "all"
    names = ["api", "worker", "scraper"] if split else ["all"]
    parts = [_part(r, beats.get(r), now, show_errors) for r in names]

    queued = db.query(QueuedTask).filter(QueuedTask.status == "QUEUED").count()
    running = db.query(QueuedTask).filter(QueuedTask.status == "RUNNING").count()
    oldest = (db.query(QueuedTask).filter(QueuedTask.status == "QUEUED").order_by(QueuedTask.created_at).first())
    failed_today = db.query(QueuedTask).filter(
        QueuedTask.status == "FAILED",
        QueuedTask.finished_at >= now.replace(hour=0, minute=0, second=0, microsecond=0)).count()
    last = db.query(RunLog).order_by(RunLog.started_at.desc()).first()
    last_run = None
    if last:
        last_run = {"status": last.status, "trigger": last.trigger_source,
                    "started_at": _iso(last.started_at), "finished_at": _iso(last.completed_at),
                    "jobs_completed": last.jobs_completed, "jobs_failed": last.jobs_failed,
                    "businesses_new": last.businesses_new}
    order = {"stopped": 0, "warning": 1, "ok": 2}
    overall = min((p["status"] for p in parts), key=lambda s: order[s])
    return {
        "checked_at": now.isoformat(), "overall": overall, "split": split, "parts": parts,
        "queue": {"queued": queued, "running": running, "failed_today": failed_today,
                  "oldest_waiting_seconds": _age(_iso(oldest.created_at), now) if oldest else None},
        "last_run": last_run,
    }
