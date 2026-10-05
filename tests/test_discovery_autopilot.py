"""
The scraping autopilot.

Runs whole days against a fake clock and a fake scraper, so what is checked
is the behaviour asked for: rounds of five 25-job batches in one state, each
batch a different tehsil with its own categories, a different state each
round, ten batches a day run one at a time fifteen minutes apart — and a
CAPTCHA stopping everything for a cool-down instead of pressing on.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import AppSetting, Category, Job, Location, RunLog
from src.models.autopilot import DiscoveryRound
from src.services import discovery_autopilot as ap

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)

# (state, district, tehsil): Haryana has 3 districts over 6 tehsils, Punjab
# 5 tehsils, and Rajasthan a single one — as thin as the real data.
PLACES = (
    [("Haryana", f"HD{i % 3}", f"HT{i}") for i in range(6)]
    + [("Punjab", f"PD{i}", f"PT{i}") for i in range(5)]
    + [("Rajasthan", "RD0", "RT0")]
)
CATEGORIES = 146


class Clock:
    """IST 06:00 on a Monday, moved on by hand or by the fake scraper."""

    def __init__(self):
        self.t = datetime(2026, 10, 5, 0, 30, tzinfo=timezone.utc)

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


class FakeScraper:
    """Completes the batch's jobs, taking 18 minutes, unless told to hit a CAPTCHA."""

    def __init__(self, db, clock):
        self.db, self.clock = db, clock
        self.batches = []
        self.captcha_next = 0
        self.fail_next = 0       # how many coming batches fail every job

    def __call__(self, request, db):
        jobs = db.query(Job).filter(Job.job_id.in_(request.job_ids), Job.status == "PENDING").all()
        run = RunLog(run_id=str(uuid.uuid4()), trigger_source=request.trigger_source,
                     status="RUNNING", started_at=self.clock())
        db.add(run)
        self.batches.append({"request": request, "jobs": [j.job_id for j in jobs]})
        blocked = self.captcha_next > 0
        failing = self.fail_next > 0
        if failing:
            self.fail_next -= 1
        done = 0
        for i, job in enumerate(jobs):
            if blocked and i == 3:
                job.status = "BLOCKED"
                break
            if failing:
                job.status = "FAILED"
                job.error_message = "selector changed"
                job.attempt_count = (job.attempt_count or 0) + 1
                job.last_attempt_at = self.clock()
                continue
            job.status = "COMPLETED"
            done += 1
        if blocked:
            self.captcha_next -= 1
        self.clock.advance(minutes=18)
        run.status = "BLOCKED" if blocked else ("FAILED" if failing else "COMPLETED")
        run.jobs_attempted = len(jobs) if failing else done + (1 if blocked else 0)
        run.jobs_completed = done
        run.jobs_failed = len(jobs) if failing else 0
        run.businesses_new = done * 7
        run.duration_seconds = 18 * 60
        run.completed_at = self.clock()
        db.commit()
        return {"status": "blocked" if blocked else "completed", "run_id": run.run_id,
                "jobs_processed": run.jobs_attempted, "jobs_completed": done,
                "businesses_saved": done * 7}


@pytest.fixture
def db(monkeypatch):
    # Job generation is exercised elsewhere; here the jobs are laid out below.
    monkeypatch.setattr("src.services.job_manager.generate_jobs", lambda db: {})
    # Online unless a test says otherwise; never the real network.
    monkeypatch.setattr(ap, "_default_online", lambda: True)
    session = Session()
    cats = [Category(category_id=f"c{i:03d}", category_name=f"Category {i:03d}") for i in range(CATEGORIES)]
    session.add_all(cats)
    for n, (state, district, tehsil) in enumerate(PLACES):
        loc = Location(location_id=f"L{n:02d}", pincode=f"1{n:05d}", latitude=29.0, longitude=76.0,
                       state=state, district=district, tehsil=tehsil, anchor_name=f"Town {n}")
        session.add(loc)
        for c in cats:
            session.add(Job(job_id=f"{loc.location_id}{c.category_id}", location_id=loc.location_id,
                            category_id=c.category_id, status="PENDING", search_query="q"))
    session.commit()
    yield session
    session.rollback()
    for model in (DiscoveryRound, RunLog, Job, Location, Category, AppSetting):
        session.query(model).delete()
    session.commit()
    session.close()


def run_until(db, clock, scraper, stop, max_ticks=5000):
    """Steps the autopilot, sleeping for real what it asks, until stop() holds."""
    import random
    rng = random.Random(7)
    for _ in range(max_ticks):
        if stop():
            return
        wait = ap.tick(db, clock=clock, runner=scraper, rng=rng)
        clock.advance(seconds=wait)
    raise AssertionError("did not get there")


def about(delta, minutes):
    return timedelta(minutes=minutes) - timedelta(seconds=5) <= delta <= timedelta(minutes=minutes)


def switch_on(db, **extra):
    ap.save_settings(db, {"enabled": True, **extra})


# --- planning -----------------------------------------------------------------

def test_a_round_is_five_batches_of_25_each_in_a_different_tehsil(db):
    plan = ap.plan_round(db, "Haryana", 5, 25)
    assert len(plan) == 5
    assert all(len(b["job_ids"]) == 25 for b in plan)
    assert len({b["tehsil"] for b in plan}) == 5, "every batch in its own tehsil"
    assert len({b["district"] for b in plan[:3]}) == 3, "a new district while any are unused"
    cats = [c for b in plan for c in b["categories"]]
    assert len(cats) == len(set(cats)) == 125, "no category twice in a round"


def test_a_state_with_one_tehsil_still_gets_fresh_categories(db):
    plan = ap.plan_round(db, "Rajasthan", 5, 25)
    assert len(plan) == 5 and {b["tehsil"] for b in plan} == {"RT0"}
    cats = [c for b in plan for c in b["categories"]]
    assert len(cats) == len(set(cats))


# --- a day ----------------------------------------------------------------------

def test_rounds_run_back_to_back_with_a_gap_and_a_new_state(db):
    clock = Clock()
    scraper = FakeScraper(db, clock)
    switch_on(db)
    run_until(db, clock, scraper, lambda: db.query(DiscoveryRound).filter_by(status="COMPLETED").count() >= 2)

    first, second = db.query(DiscoveryRound).order_by(DiscoveryRound.created_at).all()[:2]
    assert first.state != second.state, "each round moves to another state"
    assert first.batches_done == 5 and all(b["status"] == "DONE" for b in first.plan)
    # Every batch ran its own planned jobs, 25 at a time.
    assert [len(b["jobs"]) for b in scraper.batches[:5]] == [25] * 5
    assert scraper.batches[0]["request"].trigger_source == "autopilot"
    # Jobs are paced with randomness, not a fixed beat.
    assert scraper.batches[0]["request"].delay_jitter_seconds > 0
    # Five minutes at least between one round finishing and the next starting.
    assert (ap._aware(second.created_at) if second.created_at.tzinfo else second.created_at) is not None
    state = ap.get_state(db)
    assert state["last_event_code"] in ("BATCH_DONE", "ROUND_DONE", "ROUND_PLANNED")
    assert state["last_event"].endswith(".")  # a sentence for people, not a log line


def test_the_gap_between_rounds_is_respected(db):
    clock = Clock()
    scraper = FakeScraper(db, clock)
    switch_on(db)
    run_until(db, clock, scraper, lambda: db.query(DiscoveryRound).filter_by(status="COMPLETED").count() == 1)
    finished = clock()
    # Straight after a round: waiting, not starting the next.
    ap.tick(db, clock=clock, runner=scraper)
    assert ap.get_state(db)["phase"] == "gap_between_rounds"
    assert db.query(DiscoveryRound).count() == 1
    clock.t = finished + timedelta(minutes=14)
    ap.tick(db, clock=clock, runner=scraper)
    assert db.query(DiscoveryRound).count() == 1, "still inside the quarter hour"
    clock.t = finished + timedelta(minutes=15, seconds=1)
    ap.tick(db, clock=clock, runner=scraper)
    assert db.query(DiscoveryRound).count() == 2


def test_ten_batches_a_day_half_an_hour_apart_and_then_it_stops(db):
    clock = Clock()
    scraper = FakeScraper(db, clock)
    switch_on(db)
    start = clock()
    run_until(db, clock, scraper, lambda: ap.get_state(db)["phase"] == "daily_target_reached")

    # The target is checked between rounds, so the day ends on a whole round.
    assert ap.batches_today(db, clock()) == 10
    assert len(scraper.batches) == 10
    # Rotating through the states, never the same one twice running.
    rounds = db.query(DiscoveryRound).order_by(DiscoveryRound.created_at).all()
    assert len(rounds) == 2
    assert all(a.state != b.state for a, b in zip(rounds, rounds[1:]))

    # One at a time, and never sooner than a quarter of an hour after the last one
    # ended — inside a round and across the round boundary alike.
    runs = db.query(RunLog).order_by(RunLog.started_at).all()
    for earlier, later in zip(runs, runs[1:]):
        gap = ap._aware(later.started_at) - ap._aware(earlier.completed_at)
        assert gap >= timedelta(minutes=15), f"only {gap} between two batches"
        assert gap < timedelta(minutes=17)
    # Ten 18-minute batches and nine quarter-hour gaps: about five and a quarter hours.
    assert clock() - start < timedelta(hours=6)

    # Nothing more today; the next IST day it carries on.
    done = len(scraper.batches)
    # It re-checks at most every ten minutes, so a day's wait is ~150 checks.
    for _ in range(300):
        clock.advance(seconds=ap.tick(db, clock=clock, runner=scraper))
        if len(scraper.batches) > done:
            break
    assert len(scraper.batches) > done
    assert clock().astimezone(ap.IST).date() > start.astimezone(ap.IST).date()


def test_it_can_keep_going_past_the_target(db):
    clock = Clock()
    scraper = FakeScraper(db, clock)
    switch_on(db, daily_batch_target=5, continue_after_target=True)
    run_until(db, clock, scraper, lambda: len(scraper.batches) >= 12)
    assert ap.get_state(db)["phase"] != "daily_target_reached"


# --- CAPTCHA --------------------------------------------------------------------

def test_a_captcha_stops_everything_for_a_growing_cool_down(db):
    clock = Clock()
    scraper = FakeScraper(db, clock)
    switch_on(db)
    scraper.captcha_next = 2

    run_until(db, clock, scraper, lambda: len(scraper.batches) == 1)
    state = ap.get_state(db)
    blocked_at = clock()
    assert state["captcha_level"] == 1
    # The loop reads the clock one step after the batch ends, hence "about".
    assert about(ap._parse(state["cooldown_until"]) - blocked_at, minutes=30)
    # The blocked job is back in the queue, and the batch will be tried again.
    assert db.query(Job).filter(Job.status == "BLOCKED").count() == 0
    rnd = db.query(DiscoveryRound).one()
    assert rnd.plan[0]["status"] == "PLANNED" and rnd.plan[0]["blocks"] == 1

    # Nothing runs during the cool-down.
    for _ in range(10):
        ap.tick(db, clock=clock, runner=scraper)
        clock.advance(minutes=2)
    assert len(scraper.batches) == 1 and ap.get_state(db)["phase"] == "captcha_cooldown"

    # Second CAPTCHA in a row: an hour, and the pace slows.
    run_until(db, clock, scraper, lambda: len(scraper.batches) == 2)
    state = ap.get_state(db)
    assert state["captcha_level"] == 2
    assert about(ap._parse(state["cooldown_until"]) - clock(), minutes=60)
    assert clock() - blocked_at >= timedelta(minutes=30)

    run_until(db, clock, scraper, lambda: len(scraper.batches) == 3)
    slowed = scraper.batches[2]["request"]
    assert slowed.delay_between_jobs_seconds == pytest.approx(4.0 * 2)
    # The retried batch picked up where it stopped: only its unfinished jobs.
    assert len(scraper.batches[2]["jobs"]) == 25 - 3 - 3

    # Three clean batches reset the ladder.
    run_until(db, clock, scraper, lambda: len(scraper.batches) == 5)
    assert ap.get_state(db)["captcha_level"] == 0


def test_a_batch_that_keeps_hitting_captchas_is_set_aside(db):
    clock = Clock()
    scraper = FakeScraper(db, clock)
    switch_on(db)
    scraper.captcha_next = 3
    run_until(db, clock, scraper, lambda: len(scraper.batches) == 4)
    rnd = db.query(DiscoveryRound).one()
    assert rnd.plan[0]["status"] == "SKIPPED"
    assert scraper.batches[3]["request"].job_ids == rnd.plan[1]["job_ids"]


# --- control ----------------------------------------------------------------------

def test_off_means_nothing_runs(db):
    clock = Clock()
    scraper = FakeScraper(db, clock)
    for _ in range(5):
        clock.advance(seconds=ap.tick(db, clock=clock, runner=scraper))
    assert scraper.batches == [] and ap.get_state(db)["phase"] == "off"


def test_pressing_stop_switches_the_autopilot_off(db):
    clock = Clock()
    switch_on(db)

    def stopped(request, db):
        return {"status": "cancelled", "run_id": None, "jobs_completed": 0, "businesses_saved": 0}

    ap.tick(db, clock=clock, runner=stopped)   # plans the round
    ap.tick(db, clock=clock, runner=stopped)   # runs its first batch, which is stopped
    assert ap.get_settings(db)["enabled"] is False
    assert db.query(DiscoveryRound).one().plan[0]["status"] == "PLANNED"


def test_it_waits_for_a_batch_started_by_hand(db):
    clock = Clock()
    scraper = FakeScraper(db, clock)
    switch_on(db)
    db.add(RunLog(run_id="manual", trigger_source="dashboard_ui", status="RUNNING", started_at=clock()))
    db.commit()
    ap.tick(db, clock=clock, runner=scraper)
    assert ap.get_state(db)["phase"] == "waiting_for_other_run" and scraper.batches == []


def test_a_restart_resumes_the_round_it_was_in(db):
    clock = Clock()
    scraper = FakeScraper(db, clock)
    switch_on(db)
    ap.tick(db, clock=clock, runner=scraper)
    rnd = db.query(DiscoveryRound).one()
    # Killed mid-batch: a job and a run left RUNNING, the batch marked RUNNING.
    plan = [dict(b) for b in rnd.plan]
    plan[0]["status"] = "RUNNING"
    rnd.plan = plan
    db.query(Job).filter(Job.job_id == plan[0]["job_ids"][0]).update({"status": "RUNNING"})
    db.add(RunLog(run_id="orphan", trigger_source="autopilot", status="RUNNING", started_at=clock()))
    db.commit()

    assert ap.recover_after_restart(db) == {"jobs": 1, "runs": 1, "batches": 1}
    db.refresh(rnd)
    assert rnd.plan[0]["status"] == "PLANNED"
    assert db.query(RunLog).filter_by(run_id="orphan").one().status == "INTERRUPTED"
    ap.tick(db, clock=clock, runner=scraper)
    assert scraper.batches[0]["request"].job_ids == plan[0]["job_ids"]
    assert db.query(DiscoveryRound).count() == 1


def test_settings_are_validated(db):
    with pytest.raises(ValueError):
        ap.save_settings(db, {"batch_size": 0})
    with pytest.raises(ValueError):
        ap.save_settings(db, {"gap_between_batches_seconds": [200, 100]})
    with pytest.raises(ValueError):
        ap.save_settings(db, {"nonsense": 1})


def test_status_reports_progress(db):
    clock = Clock()
    scraper = FakeScraper(db, clock)
    switch_on(db)
    run_until(db, clock, scraper, lambda: len(scraper.batches) == 2)
    s = ap.status(db)
    assert s["rounds"][0]["plan"][0]["jobs_finished"] == 25
    assert "job_ids" not in s["rounds"][0]["plan"][0]
    assert s["pending_by_state"]


def test_a_batch_runs_exactly_its_planned_jobs():
    from src.routers.discovery import BatchRequest, apply_target_filters
    s = Session()
    try:
        s.add(Job(job_id="A1", location_id="X", category_id="c", status="PENDING", search_query="q"))
        s.add(Job(job_id="A2", location_id="X", category_id="d", status="PENDING", search_query="q"))
        s.commit()
        q = apply_target_filters(s.query(Job).filter(Job.status == "PENDING"), BatchRequest(job_ids=["A2"]))
        assert [j.job_id for j in q.all()] == ["A2"]
    finally:
        s.query(Job).delete()
        s.commit()
        s.close()


# --- a change of pace ---------------------------------------------------------

def test_saved_settings_adopt_the_new_pace_once_and_are_switched_off(db):
    """
    The pace lives in the database once the Pacing form is used, so new
    defaults alone would never reach a server that has saved settings. And a
    deploy must not be what starts a new pace running.
    """
    # A server on the old pace, switched on, with a choice of its own.
    ap._write(db, ap.SETTINGS_KEY, {**ap.DEFAULTS, "enabled": True, "daily_batch_target": 30,
                                    "gap_between_batches_seconds": [45, 150],
                                    "gap_between_rounds_minutes": 5, "batch_size": 20})
    assert ap.adopt_pace(db) is True

    s = ap.get_settings(db)
    assert s["enabled"] is False
    assert s["daily_batch_target"] == 10
    assert s["gap_between_batches_seconds"] == [900, 900]
    assert s["gap_between_rounds_minutes"] == 15
    assert s["batch_size"] == 20, "what the pace does not cover is left alone"
    assert "Switched off" in ap.get_state(db)["last_event"]

    # Only once: a later start leaves a person's own choices in place.
    ap.save_settings(db, {"enabled": True, "daily_batch_target": 12})
    assert ap.adopt_pace(db) is False
    assert ap.get_settings(db)["enabled"] is True
    assert ap.get_settings(db)["daily_batch_target"] == 12


def test_switched_off_it_runs_nothing(db):
    clock = Clock()
    scraper = FakeScraper(db, clock)
    ap.adopt_pace(db)
    for _ in range(20):
        clock.advance(seconds=ap.tick(db, clock=clock, runner=scraper))
    assert scraper.batches == [] and db.query(DiscoveryRound).count() == 0
    assert ap.get_state(db)["phase"] == "off"


# --- no internet --------------------------------------------------------------

class Link:
    """The server's connection, up or down as a test says."""

    def __init__(self, up=True):
        self.up = up
        self.checks = 0

    def __call__(self):
        self.checks += 1
        return self.up


def test_nothing_is_scraped_while_the_internet_is_down(db):
    """
    On 3 October the connection dropped and thirty batches a day ran into it
    for two days, failing every job. A dead connection now starts nothing.
    """
    clock, link = Clock(), Link(up=False)
    scraper = FakeScraper(db, clock)
    switch_on(db)
    for _ in range(400):
        clock.advance(seconds=ap.tick(db, clock=clock, runner=scraper, online=link))

    assert scraper.batches == [], "no batch is started into a dead connection"
    assert db.query(Job).filter(Job.status != "PENDING").count() == 0, "no job is used up"
    assert ap.get_state(db)["phase"] == "no_internet"
    assert ap.batches_today(db, clock()) == 0


def test_the_connection_is_rechecked_at_growing_intervals(db):
    clock, link = Clock(), Link(up=False)
    scraper = FakeScraper(db, clock)
    switch_on(db)
    times = []
    seen = 0
    for _ in range(3000):
        clock.advance(seconds=ap.tick(db, clock=clock, runner=scraper, online=link))
        if link.checks > seen:
            seen = link.checks
            times.append(clock())
        if len(times) == 6:
            break
    gaps = [round((b - a).total_seconds() / 60) for a, b in zip(times, times[1:])]
    assert gaps == [5, 15, 30, 60, 60], gaps


def test_it_carries_on_by_itself_when_the_connection_returns(db):
    clock, link = Clock(), Link(up=False)
    scraper = FakeScraper(db, clock)
    switch_on(db)
    for _ in range(50):
        clock.advance(seconds=ap.tick(db, clock=clock, runner=scraper, online=link))
    assert scraper.batches == []

    link.up = True
    run_until_with(db, clock, scraper, link, lambda: len(scraper.batches) == 2)
    state = ap.get_state(db)
    assert state["offline_level"] == 0 and state["offline_until"] is None
    assert ap.batches_today(db, clock()) == 2


def run_until_with(db, clock, scraper, link, stop, max_ticks=5000):
    for _ in range(max_ticks):
        if stop():
            return
        clock.advance(seconds=ap.tick(db, clock=clock, runner=scraper, online=link))
    raise AssertionError("did not get there")


def test_a_batch_that_loses_the_connection_is_retried_and_not_counted(db):
    """Dropping mid-batch must not use up the batch, or one of the day's ten."""
    clock, link = Clock(), Link(up=True)
    scraper = FakeScraper(db, clock)
    calls = []

    def drops_once(request, session):
        calls.append(list(request.job_ids))
        if len(calls) == 1:
            # What _run_batch reports when the connection goes mid-batch.
            run = RunLog(run_id=str(uuid.uuid4()), trigger_source=request.trigger_source,
                         status="OFFLINE", started_at=clock(), jobs_attempted=3)
            session.add(run)
            session.commit()
            link.up = False
            return {"status": "blocked", "offline": True, "run_id": run.run_id,
                    "jobs_processed": 3, "jobs_completed": 0, "businesses_saved": 0}
        return scraper(request, session)

    switch_on(db)
    run_until_with(db, clock, drops_once, link, lambda: ap.get_state(db)["phase"] == "no_internet")
    assert ap.batches_today(db, clock()) == 0, "a batch that scraped nothing is not one of the day's"
    assert ap.get_state(db).get("captcha_level", 0) == 0, "a dead connection is not a CAPTCHA"

    link.up = True
    run_until_with(db, clock, drops_once, link, lambda: len(calls) == 2)
    assert calls[1] == calls[0], "the same batch is tried again"


# --- failed jobs get another go -----------------------------------------------

DNS = "Navigation timeout or network failure: Page.goto: net::ERR_NAME_NOT_RESOLVED"


def fail(db, job_id, error, attempts):
    db.query(Job).filter(Job.job_id == job_id).update(
        {"status": "FAILED", "error_message": error, "attempt_count": attempts,
         "last_attempt_at": datetime(2026, 10, 4, tzinfo=timezone.utc)})


def test_failed_jobs_go_back_in_the_queue_by_why_they_failed(db):
    fail(db, "L00c000", DNS, 1)                       # the outage: never really tried
    fail(db, "L00c001", "selector changed", 1)        # a real failure, attempts left
    fail(db, "L00c002", "selector changed", 3)        # out of attempts
    db.commit()

    assert ap.requeue_failed_jobs(db) == {"network": 1, "other": 1, "total": 2}
    jobs = {j.job_id: j for j in db.query(Job).filter(Job.job_id.in_(["L00c000", "L00c001", "L00c002"]))}
    assert jobs["L00c000"].status == "PENDING" and jobs["L00c000"].attempt_count == 0
    assert jobs["L00c001"].status == "PENDING" and jobs["L00c001"].attempt_count == 1
    assert jobs["L00c002"].status == "FAILED", "a search that fails every time is left alone"


def test_retries_ride_in_the_ordinary_batches_at_the_same_pace(db):
    """No extra batches: a failed job is scraped inside the day's ten."""
    failed_ids = [f"L00c{i:03d}" for i in range(40)]
    for job_id in failed_ids:
        fail(db, job_id, DNS, 1)
    db.commit()

    clock = Clock()
    scraper = FakeScraper(db, clock)
    switch_on(db, states=["Haryana"])
    run_until(db, clock, scraper, lambda: ap.get_state(db)["phase"] == "daily_target_reached")

    assert len(scraper.batches) == 10, "still ten batches, not ten plus retries"
    assert db.query(Job).filter(Job.status == "FAILED").count() == 0
    scraped = {j for b in scraper.batches for j in b["jobs"]}
    # Forty retries in one town, twenty-five to a batch and a town once per
    # round: all of them are done in the day's two rounds, ahead of the
    # hundreds of jobs there that were never tried.
    assert set(failed_ids) <= scraped, "every failed job was scraped again today"
    first = scraper.batches[0]["jobs"]
    assert set(first) <= set(failed_ids), "the first batch is made of retries"
    runs = db.query(RunLog).order_by(RunLog.started_at).all()
    assert all(ap._aware(b.started_at) - ap._aware(a.completed_at) >= timedelta(minutes=15)
               for a, b in zip(runs, runs[1:]))


def test_retrying_can_be_switched_off(db):
    fail(db, "L00c000", DNS, 1)
    db.commit()
    clock = Clock()
    scraper = FakeScraper(db, clock)
    switch_on(db, retry_failed_jobs=False)
    run_until(db, clock, scraper, lambda: len(scraper.batches) == 1)
    assert db.query(Job).filter(Job.job_id == "L00c000").one().status == "FAILED"


# --- a failed batch is not one of the day's ------------------------------------

def test_a_batch_whose_jobs_all_failed_does_not_count(db):
    """Ten batches a day means ten that scraped something."""
    clock = Clock()
    scraper = FakeScraper(db, clock)
    scraper.fail_next = 3
    switch_on(db)
    run_until(db, clock, scraper, lambda: ap.get_state(db)["phase"] == "daily_target_reached")

    assert len(scraper.batches) == 13, "three failed batches, then the day's ten"
    assert ap.batches_today(db, clock()) == 10
    assert ap.failed_batches_today(db, clock()) == 3
    status = ap.status(db)["today"]
    assert status["batches_done"] == 10 and status["batches_failed"] == 3
    # Still one at a time, a quarter of an hour apart, failed ones included.
    runs = db.query(RunLog).order_by(RunLog.started_at).all()
    assert all(ap._aware(b.started_at) - ap._aware(a.completed_at) >= timedelta(minutes=15)
               for a, b in zip(runs, runs[1:]))


def test_a_day_of_nothing_but_failures_stops_itself(db):
    """Uncounted must not mean unlimited: it stops and asks to be looked at."""
    clock = Clock()
    scraper = FakeScraper(db, clock)
    scraper.fail_next = 999
    switch_on(db)
    run_until(db, clock, scraper, lambda: ap.get_state(db)["phase"] == "too_many_failures")

    assert len(scraper.batches) == 10, "as many failed batches as the day's target, no more"
    assert ap.batches_today(db, clock()) == 0
    assert "failed completely" in ap.get_state(db)["last_event"]
    done = len(scraper.batches)
    for _ in range(20):
        clock.advance(seconds=ap.tick(db, clock=clock, runner=scraper))
        if clock().astimezone(ap.IST).date() > datetime(2026, 10, 5).date():
            break
    assert len(scraper.batches) == done or clock().astimezone(ap.IST).date() > datetime(2026, 10, 5).date()
