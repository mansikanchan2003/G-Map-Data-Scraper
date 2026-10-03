"""
The scraping autopilot: runs discovery on its own, round after round.

A ROUND is one state and a handful of batches run one after another. Each
batch is one tehsil and its own categories — a different tehsil (and, where
the state has them, a different district) for every batch, and no category
repeated within the round — so a round spreads across the state instead of
draining one town. When a round's batches are done the autopilot waits,
then starts the next round in a different state.

It stops for the day at a batch target, finishing the round it is in.

Avoiding Google's CAPTCHA is done by behaving less like a machine, never by
getting around one:
  * every pause — between jobs, batches and rounds — is randomised;
  * the browser reports its real version and an Indian locale;
  * a CAPTCHA stops everything for a cool-down that grows each time it
    recurs (30 min, 1 h, 2 h, 4 h), slows the pace afterwards, and puts the
    blocked job back in the queue. A few clean batches bring it back down.

Everything the autopilot is doing lives in the database — the settings, its
runtime state and every round's plan — so a restart resumes rather than
repeats, and the dashboard shows exactly what it is up to.

The loop is a single daemon thread in the backend process. Each step is
`tick()`, which does one thing and says how long to wait before the next;
the thread only calls it and sleeps.
"""
import json
import logging
import random
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models import AppSetting, Category, Job, Location, RunLog
from src.models.autopilot import DiscoveryRound

logger = logging.getLogger("gmap_scraper.autopilot")

IST = timezone(timedelta(hours=5, minutes=30))
TRIGGER = "autopilot"
SETTINGS_KEY = "discovery_autopilot"
STATE_KEY = "discovery_autopilot_state"

DEFAULTS: Dict = {
    "enabled": False,
    "batch_size": 25,
    "batches_per_round": 5,
    # Thirty minutes between any two batches, whether or not a round ends
    # between them: the two gaps are the same so the pace is one batch at a
    # time, half an hour apart.
    "gap_between_rounds_minutes": 30,
    # The pause between the batches of a round, as a [low, high] range.
    "gap_between_batches_seconds": [1800, 1800],
    # After each job: this many seconds plus up to the jitter, at random.
    "job_delay_seconds": 4.0,
    "job_delay_jitter_seconds": 6.0,
    "daily_batch_target": 10,
    # Past the target, keep going instead of stopping for the day.
    "continue_after_target": False,
    # Limit rounds to these states; empty means every state with work left.
    "states": [],
}

# The pace is saved in the database once anyone uses the Pacing form, so a
# change to DEFAULTS alone never reaches a server that has saved settings.
# Raising this number makes the next start adopt PACE once, and switches the
# autopilot off as it does: a new pace is something a person turns on, not
# something a deploy starts running.
#   2: ten batches a day, one at a time, thirty minutes apart (was thirty a
#      day, 45-150 s apart).
PACE_VERSION = 2
PACE_VERSION_KEY = "discovery_autopilot_pace_version"
PACE_KEYS = ("daily_batch_target", "gap_between_batches_seconds", "gap_between_rounds_minutes",
             "continue_after_target")

# How long to stop after a CAPTCHA, by how many have happened in a row.
COOLDOWN_MINUTES = [30, 60, 120, 240]
# Clean batches after a CAPTCHA before the cool-down ladder resets.
CLEAN_BATCHES_TO_RESET = 3
# A batch blocked this many times is set aside rather than retried forever.
MAX_BLOCKS_PER_BATCH = 3
# A RUNNING run this old is a leftover, not something to wait for.
STALE_RUN = timedelta(hours=2)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _parse(value: Optional[str]) -> Optional[datetime]:
    return _aware(datetime.fromisoformat(value)) if value else None


# ---------------------------------------------------------------------------
# Settings and runtime state
# ---------------------------------------------------------------------------

def _read(db: Session, key: str) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    try:
        return json.loads(row.value) if row and row.value else {}
    except ValueError:
        return {}


def _write(db: Session, key: str, value: dict) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        row = AppSetting(key=key)
        db.add(row)
    row.value = json.dumps(value)
    db.commit()


def get_settings(db: Session) -> dict:
    return {**DEFAULTS, **_read(db, SETTINGS_KEY)}


def save_settings(db: Session, updates: dict) -> dict:
    """Applies a partial update, refusing values that would misbehave."""
    current = get_settings(db)
    limits = {
        "batch_size": (1, 100), "batches_per_round": (1, 20),
        "gap_between_rounds_minutes": (0, 240), "daily_batch_target": (1, 200),
        "job_delay_seconds": (0.0, 60.0), "job_delay_jitter_seconds": (0.0, 60.0),
    }
    for key, value in updates.items():
        if key not in DEFAULTS:
            raise ValueError(f"Unknown setting: {key}")
        if key in limits:
            lo, hi = limits[key]
            if not (lo <= value <= hi):
                raise ValueError(f"{key} must be between {lo} and {hi}")
        if key == "gap_between_batches_seconds":
            if len(value) != 2 or not (0 <= value[0] <= value[1] <= 3600):
                raise ValueError("gap_between_batches_seconds must be [low, high] seconds, low <= high")
        current[key] = value
    _write(db, SETTINGS_KEY, {k: current[k] for k in DEFAULTS})
    return current


def adopt_pace(db: Session) -> bool:
    """
    Brings saved settings onto the current pace, once per PACE_VERSION.

    Returns True when it changed anything. The autopilot is left switched
    off, so the new pace starts only when someone turns it on.
    """
    seen = (_read(db, PACE_VERSION_KEY) or {}).get("version", 1)
    if seen >= PACE_VERSION:
        return False
    current = get_settings(db)
    for key in PACE_KEYS:
        current[key] = DEFAULTS[key]
    current["enabled"] = False
    _write(db, SETTINGS_KEY, {k: current[k] for k in DEFAULTS})
    _write(db, PACE_VERSION_KEY, {"version": PACE_VERSION})
    state = get_state(db)
    state["next_batch_at"] = None
    _event(state, "PACE_CHANGED",
           f"Pace changed to {DEFAULTS['daily_batch_target']} batches a day, "
           f"{DEFAULTS['gap_between_rounds_minutes']} minutes apart. Switched off until turned on again.")
    _write(db, STATE_KEY, state)
    return True


def get_state(db: Session) -> dict:
    return {"phase": "off", "captcha_level": 0, "clean_streak": 0, "cooldown_until": None,
            "next_batch_at": None, "last_event": None, "last_event_at": None, **_read(db, STATE_KEY)}


def _event(state: dict, code: str, message: str) -> None:
    """Records what just happened: a sentence for the dashboard, a code for the logs."""
    state["last_event"] = message
    state["last_event_code"] = code
    state["last_event_at"] = _iso(_now())
    logger.info(f"autopilot event={code} {message}")


# ---------------------------------------------------------------------------
# Choosing where to go
# ---------------------------------------------------------------------------

def pending_by_state(db: Session) -> Dict[str, int]:
    rows = (
        db.query(Location.state, func.count(Job.job_id))
        .join(Job, Job.location_id == Location.location_id)
        .filter(Job.status == "PENDING", Location.state.isnot(None))
        .group_by(Location.state)
        .all()
    )
    return {state: n for state, n in rows if n}


def choose_state(db: Session, settings: dict) -> Optional[str]:
    """
    The state for the next round: never the one just visited if another has
    work, and otherwise the one visited longest ago, most work left first.
    """
    pending = pending_by_state(db)
    allowed = {s.lower() for s in settings.get("states") or []}
    if allowed:
        pending = {s: n for s, n in pending.items() if s.lower() in allowed}
    if not pending:
        return None

    last_visit = dict(
        db.query(DiscoveryRound.state, func.max(DiscoveryRound.created_at))
        .group_by(DiscoveryRound.state).all()
    )
    previous = (db.query(DiscoveryRound.state)
                .order_by(DiscoveryRound.created_at.desc()).limit(1).scalar())
    candidates = [s for s in pending if s != previous] or list(pending)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return min(candidates, key=lambda s: (_aware(last_visit.get(s)) or epoch, -pending[s], s))


def plan_round(db: Session, state: str, batches: int, batch_size: int,
               rng: Optional[random.Random] = None) -> List[dict]:
    """
    Splits a state's pending work into batches, one tehsil each.

    Each batch goes to the location that best keeps the round spread out: a
    tehsil not yet used, in a district not yet used, with enough untouched
    categories to fill a batch. Categories are never repeated within a round.
    A state with fewer tehsils than batches reuses them, still with fresh
    categories.
    """
    rng = rng or random.Random()
    rows = (
        db.query(Job.job_id, Job.category_id, Category.category_name, Location.location_id,
                 Location.anchor_name, Location.pincode, Location.district, Location.tehsil)
        .join(Location, Location.location_id == Job.location_id)
        .join(Category, Category.category_id == Job.category_id)
        .filter(Job.status == "PENDING", func.lower(Location.state) == state.lower())
        .all()
    )

    locations: Dict[str, dict] = {}
    for job_id, cat_id, cat_name, loc_id, anchor, pincode, district, tehsil in rows:
        loc = locations.setdefault(loc_id, {
            "location_id": loc_id, "anchor": anchor, "pincode": pincode,
            "district": district, "tehsil": tehsil, "jobs": {},
        })
        loc["jobs"][cat_id] = (job_id, cat_name)

    used_cats, used_locs, used_tehsils, used_districts = set(), set(), set(), set()
    plan = []
    for number in range(1, batches + 1):
        def available(loc):
            return [c for c in loc["jobs"] if c not in used_cats]

        options = [l for l in locations.values() if available(l)]
        if not options:
            break

        def spread(loc):
            tehsil = (loc["district"], loc["tehsil"] or loc["anchor"])
            return (
                loc["location_id"] in used_locs,
                tehsil in used_tehsils,
                loc["district"] in used_districts,
                -min(len(available(loc)), batch_size),
                rng.random(),
            )

        pick = min(options, key=spread)
        cats = available(pick)
        rng.shuffle(cats)
        chosen = cats[:batch_size]
        plan.append({
            "batch": number,
            "location_id": pick["location_id"],
            "anchor": pick["anchor"],
            "pincode": pick["pincode"],
            "district": pick["district"],
            "tehsil": pick["tehsil"],
            "job_ids": [pick["jobs"][c][0] for c in chosen],
            "categories": sorted(pick["jobs"][c][1] for c in chosen),
            "status": "PLANNED",
            "blocks": 0,
            "run_id": None, "started_at": None, "completed_at": None,
            "jobs_completed": 0, "businesses_saved": 0,
        })
        used_cats.update(chosen)
        used_locs.add(pick["location_id"])
        used_tehsils.add((pick["district"], pick["tehsil"] or pick["anchor"]))
        used_districts.add(pick["district"])
    return plan


# ---------------------------------------------------------------------------
# Bookkeeping
# ---------------------------------------------------------------------------

def _ist_midnight(now: datetime) -> datetime:
    local = now.astimezone(IST)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def batches_today(db: Session, now: Optional[datetime] = None) -> int:
    """Autopilot batches that ran today, counting the day in IST."""
    now = now or _now()
    return (
        db.query(RunLog)
        .filter(RunLog.trigger_source == TRIGGER, RunLog.jobs_attempted > 0,
                RunLog.started_at >= _ist_midnight(now))
        .count()
    )


def _other_run_active(db: Session, now: datetime) -> bool:
    """A batch someone started by hand, which the autopilot must not overlap."""
    running = db.query(RunLog).filter(RunLog.status == "RUNNING").all()
    return any(now - _aware(r.started_at) < STALE_RUN for r in running)


def recover_after_restart(db: Session) -> dict:
    """
    Tidies what a restart left behind, before the loop starts.

    Nothing can be mid-run in a process that has only just started, so any
    RUNNING job or run is an orphan of the previous one. Jobs go back to the
    queue, runs are closed as interrupted, and a batch caught mid-flight is
    planned again — its unfinished jobs are still pending, so it resumes.
    """
    jobs = db.query(Job).filter(Job.status == "RUNNING").update(
        {"status": "PENDING", "error_message": "Interrupted by a restart"}, synchronize_session=False)
    runs = db.query(RunLog).filter(RunLog.status.in_(("RUNNING", "CANCELLING"))).update(
        {"status": "INTERRUPTED", "completed_at": _now()}, synchronize_session=False)
    rounds = 0
    for r in db.query(DiscoveryRound).filter(DiscoveryRound.status == "ACTIVE").all():
        plan = [dict(b) for b in r.plan]
        for b in plan:
            if b["status"] == "RUNNING":
                b["status"] = "PLANNED"
                rounds += 1
        r.plan = plan
    db.commit()
    if jobs or runs or rounds:
        logger.info(f"autopilot event=RECOVERED jobs={jobs} runs={runs} batches={rounds}")
    return {"jobs": jobs, "runs": runs, "batches": rounds}


def _default_runner(request, db: Session) -> dict:
    from src.routers.discovery import _run_batch
    return _run_batch(request, db)


# ---------------------------------------------------------------------------
# One step
# ---------------------------------------------------------------------------

def tick(db: Session, clock: Callable[[], datetime] = _now,
         runner: Callable = _default_runner, rng: Optional[random.Random] = None) -> float:
    """
    Does the next thing the autopilot should do, and returns how many
    seconds to wait before being called again.

    The clock is read again after a batch runs, since a batch takes a
    quarter of an hour and every gap is measured from when it finished.
    """
    from src.routers.discovery import BatchRequest
    from src.services import job_manager

    now = clock()
    rng = rng or random.Random()
    settings = get_settings(db)
    state = get_state(db)

    def done(phase: str, wait: float, **extra) -> float:
        state.update(phase=phase, **extra)
        _write(db, STATE_KEY, state)
        return max(1.0, wait)

    if not settings["enabled"]:
        return done("off", 30)

    cooldown = _parse(state.get("cooldown_until"))
    if cooldown and now < cooldown:
        return done("captcha_cooldown", min(60, (cooldown - now).total_seconds()))

    if _other_run_active(db, now):
        return done("waiting_for_other_run", 30)

    active = (db.query(DiscoveryRound).filter(DiscoveryRound.status == "ACTIVE")
              .order_by(DiscoveryRound.created_at).first())

    # --- no round under way: start one, if it is time ----------------------
    if active is None:
        target = settings["daily_batch_target"]
        if batches_today(db, now) >= target and not settings["continue_after_target"]:
            tomorrow = _ist_midnight(now) + timedelta(days=1)
            return done("daily_target_reached", min(600, (tomorrow - now).total_seconds()),
                        next_round_at=_iso(tomorrow))

        last = (db.query(DiscoveryRound).filter(DiscoveryRound.completed_at.isnot(None))
                .order_by(DiscoveryRound.completed_at.desc()).first())
        if last:
            ready = _aware(last.completed_at) + timedelta(minutes=settings["gap_between_rounds_minutes"])
            if now < ready:
                return done("gap_between_rounds", min(30, (ready - now).total_seconds()),
                            next_round_at=_iso(ready))

        # New PINs added since the last round only have jobs once generated.
        job_manager.generate_jobs(db)
        state_name = choose_state(db, settings)
        if not state_name:
            return done("no_pending_jobs", 600)
        plan = plan_round(db, state_name, settings["batches_per_round"], settings["batch_size"], rng)
        if not plan:
            return done("no_pending_jobs", 600)
        # Stamped with the autopilot's own clock, which the state rotation
        # orders by — two rounds made in the same second must not tie.
        db.add(DiscoveryRound(round_id=uuid.uuid4().hex, state=state_name, status="ACTIVE",
                              plan=plan, created_at=now))
        _event(state, "ROUND_PLANNED",
               f"New round in {state_name}: {len(plan)} batches across "
               f"{', '.join(str(b['tehsil'] or b['anchor']) for b in plan)}.")
        db.commit()
        state["next_batch_at"] = None
        return done("starting_round", 1, next_round_at=None)

    # --- a round is under way: run its next batch ---------------------------
    plan = [dict(b) for b in active.plan]
    upcoming = next((b for b in plan if b["status"] == "PLANNED"), None)
    if upcoming is None:
        active.status = "COMPLETED" if active.batches_done else "ABANDONED"
        active.completed_at = now
        db.commit()
        _event(state, "ROUND_DONE", f"Round in {active.state} finished: {active.batches_done} batches.")
        return done("round_complete", 1)

    next_at = _parse(state.get("next_batch_at"))
    if next_at and now < next_at:
        return done("gap_between_batches", min(30, (next_at - now).total_seconds()))

    # Slower after a CAPTCHA, by half again per level.
    slow = 1 + 0.5 * state.get("captcha_level", 0)
    upcoming.update(status="RUNNING", started_at=_iso(now))
    active.plan = plan
    state.update(phase="running_batch", current_round=active.round_id, current_batch=upcoming["batch"])
    _write(db, STATE_KEY, state)
    db.commit()

    result = runner(BatchRequest(
        batch_size=len(upcoming["job_ids"]),
        job_ids=upcoming["job_ids"],
        trigger_source=TRIGGER,
        delay_between_jobs_seconds=min(60.0, settings["job_delay_seconds"] * slow),
        delay_jitter_seconds=min(120.0, settings["job_delay_jitter_seconds"] * slow),
    ), db)

    db.refresh(active)
    plan = [dict(b) for b in active.plan]
    batch = next(b for b in plan if b["batch"] == upcoming["batch"])
    batch["run_id"] = result.get("run_id") or batch.get("run_id")
    batch["jobs_completed"] = batch.get("jobs_completed", 0) + result.get("jobs_completed", 0)
    batch["businesses_saved"] = batch.get("businesses_saved", 0) + result.get("businesses_saved", 0)
    outcome = result.get("status")
    finished = clock()

    if outcome == "blocked":
        # Stop, cool down for longer each time, and try this batch again
        # afterwards: its unfinished jobs are still pending.
        level = state.get("captcha_level", 0)
        minutes = COOLDOWN_MINUTES[min(level, len(COOLDOWN_MINUTES) - 1)]
        db.query(Job).filter(Job.job_id.in_(batch["job_ids"]), Job.status == "BLOCKED").update(
            {"status": "PENDING", "blocked_reason": None,
             "error_message": "CAPTCHA; returned to the queue after a cool-down"},
            synchronize_session=False)
        batch["blocks"] = batch.get("blocks", 0) + 1
        batch["status"] = "SKIPPED" if batch["blocks"] >= MAX_BLOCKS_PER_BATCH else "PLANNED"
        state.update(captcha_level=level + 1, clean_streak=0,
                     cooldown_until=_iso(finished + timedelta(minutes=minutes)))
        _event(state, "CAPTCHA",
               f"Google showed a CAPTCHA on batch {batch['batch']} in {active.state}. "
               f"Paused for {minutes} minutes; the batch will be retried.")
    elif outcome == "cancelled":
        # Someone pressed Stop: that means stop, not skip to the next batch.
        batch["status"] = "PLANNED"
        _write(db, SETTINGS_KEY, {**settings, "enabled": False})
        _event(state, "STOPPED_BY_USER", "Stopped by hand, so the autopilot switched itself off.")
    else:
        batch.update(status="DONE", completed_at=_iso(finished))
        active.batches_done = (active.batches_done or 0) + 1
        state["clean_streak"] = state.get("clean_streak", 0) + 1
        if state["clean_streak"] >= CLEAN_BATCHES_TO_RESET:
            state["captcha_level"] = 0
        _event(state, "BATCH_DONE",
               f"Batch {batch['batch']} in {active.state} done: {batch['tehsil'] or batch['anchor']}, "
               f"{result.get('jobs_processed', 0)} jobs, {result.get('businesses_saved', 0)} new businesses.")

    low, high = settings["gap_between_batches_seconds"]
    state["next_batch_at"] = _iso(finished + timedelta(seconds=rng.uniform(low, high)))
    active.plan = plan
    db.commit()
    return done("between_batches", 1)


# ---------------------------------------------------------------------------
# What the dashboard shows
# ---------------------------------------------------------------------------

def _round_view(r: DiscoveryRound, progress: Dict[str, str]) -> dict:
    plan = []
    for b in r.plan:
        statuses = [progress.get(j) for j in b["job_ids"]]
        plan.append({**{k: v for k, v in b.items() if k != "job_ids"},
                     "jobs": len(b["job_ids"]),
                     "jobs_finished": sum(1 for s in statuses if s in ("COMPLETED", "PARTIAL", "FAILED"))})
    return {"round_id": r.round_id, "state": r.state, "status": r.status,
            "batches_done": r.batches_done, "batches": len(r.plan), "plan": plan,
            "created_at": _iso(_aware(r.created_at)), "completed_at": _iso(_aware(r.completed_at))}


def status(db: Session) -> dict:
    now = _now()
    settings = get_settings(db)
    state = get_state(db)
    if not settings["enabled"]:
        # Switched off between ticks: say so, not whatever it was last doing.
        state["phase"] = "off"
    rounds = db.query(DiscoveryRound).order_by(DiscoveryRound.created_at.desc()).limit(12).all()

    job_ids = [j for r in rounds[:3] for b in r.plan for j in b["job_ids"]]
    progress = dict(db.query(Job.job_id, Job.status).filter(Job.job_id.in_(job_ids)).all()) if job_ids else {}

    today_runs = (db.query(RunLog).filter(RunLog.trigger_source == TRIGGER,
                                          RunLog.started_at >= _ist_midnight(now)).all())
    done_today = sum(1 for r in today_runs if (r.jobs_attempted or 0) > 0)
    finished = [r for r in today_runs if r.duration_seconds]
    avg_batch = (sum(r.duration_seconds for r in finished) / len(finished)) if finished else None

    remaining = max(0, settings["daily_batch_target"] - done_today)
    eta = None
    if avg_batch and remaining and settings["enabled"]:
        per_round = settings["batches_per_round"]
        gaps = (remaining * sum(settings["gap_between_batches_seconds"]) / 2
                + (remaining / per_round) * settings["gap_between_rounds_minutes"] * 60)
        eta = _iso(now + timedelta(seconds=remaining * avg_batch + gaps))

    return {
        "settings": settings,
        "state": state,
        "now": _iso(now),
        "today": {
            "batches_done": done_today,
            "target": settings["daily_batch_target"],
            "jobs": sum(r.jobs_attempted or 0 for r in today_runs),
            "businesses_saved": sum(r.businesses_new or 0 for r in today_runs),
            "captchas": sum(1 for r in today_runs if r.status == "BLOCKED"),
            "avg_batch_seconds": round(avg_batch) if avg_batch else None,
            "target_eta": eta,
        },
        "pending_by_state": pending_by_state(db),
        "rounds": [_round_view(r, progress) for r in rounds],
    }


# ---------------------------------------------------------------------------
# The thread
# ---------------------------------------------------------------------------

_thread: Optional[threading.Thread] = None
_stop = threading.Event()


def _loop() -> None:
    from src.database import SessionLocal

    db = SessionLocal()
    try:
        adopt_pace(db)
        recover_after_restart(db)
    except Exception:
        logger.exception("autopilot event=RECOVERY_FAILED")
    finally:
        db.close()

    while not _stop.is_set():
        db = SessionLocal()
        try:
            wait = tick(db)
        except Exception:
            db.rollback()
            logger.exception("autopilot event=TICK_FAILED")
            wait = 60
        finally:
            db.close()
        _stop.wait(wait)


def start() -> None:
    """Starts the loop once per process. It idles until switched on."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="discovery-autopilot", daemon=True)
    _thread.start()
    logger.info("autopilot event=THREAD_STARTED")


def stop() -> None:
    _stop.set()
