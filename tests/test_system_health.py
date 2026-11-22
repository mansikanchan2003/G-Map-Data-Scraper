"""The Dashboard's System health: the website, the worker and the scraper, each alive or not (22 Nov 2026)."""
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app
from src.models import AppSetting
from src.services import system_health as sh

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)
NOW = datetime.now(timezone.utc)


def _beat(seconds_ago=10, threads=(("nudges", True),), errors=(), memory=(300, 2048)):
    return {"at": (NOW - timedelta(seconds=seconds_ago)).isoformat(), "started_at": (NOW - timedelta(hours=2)).isoformat(),
            "threads": [{"name": n, "label": n, "alive": a} for n, a in threads],
            "errors": [{"at": (NOW - timedelta(minutes=m)).isoformat(), "where": "x", "text": t} for m, t in errors],
            "memory": {"used_mb": memory[0], "limit_mb": memory[1]}}


def test_each_part_says_running_needs_a_look_or_stopped():
    assert sh._part("worker", _beat(), NOW, True)["status"] == "ok"
    assert sh._part("worker", None, NOW, True)["status"] == "stopped"
    silent = sh._part("scraper", _beat(seconds_ago=600), NOW, True)
    assert silent["status"] == "stopped" and "10 minutes" in silent["why"]
    dead = sh._part("worker", _beat(threads=(("nudges", False),)), NOW, True)
    assert dead["status"] == "warning" and "nudges" in dead["why"]
    full = sh._part("scraper", _beat(memory=(2900, 3072)), NOW, True)
    assert full["status"] == "warning" and "Memory nearly full" in full["why"]
    # An error in the last hour counts; an old one does not.
    erred = sh._part("api", _beat(errors=((5, "boom"), (300, "old"))), NOW, True)
    assert erred["status"] == "warning" and [e["text"] for e in erred["errors"]] == ["boom"]
    assert sh._part("api", _beat(errors=((5, "boom"),)), NOW, False)["errors"] == []


def test_the_report_reads_every_parts_heartbeat(monkeypatch):
    monkeypatch.setenv("APP_ROLE", "api")
    db = Session()
    db.query(AppSetting).delete()
    # Fresh as of now, not as of when this file was loaded: the full suite takes minutes.
    beat = _beat()
    beat["at"] = datetime.now(timezone.utc).isoformat()
    db.add(AppSetting(key="system_health:worker", value=json.dumps(beat)))
    db.commit()
    r = sh.report(db)
    by = {p["role"]: p for p in r["parts"]}
    assert r["split"] and set(by) == {"api", "worker", "scraper"}
    assert by["worker"]["status"] == "ok" and by["scraper"]["status"] == "stopped"
    assert by["api"]["seen_seconds_ago"] == 0                 # its own state, fresh
    assert r["overall"] == "stopped" and r["queue"]["queued"] == 0
    db.close()


def test_one_process_is_one_part(monkeypatch):
    monkeypatch.delenv("APP_ROLE", raising=False)
    db = Session()
    r = sh.report(db)
    assert not r["split"] and [p["role"] for p in r["parts"]] == ["all"]
    db.close()


def test_the_endpoint_answers_a_signed_in_person():
    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    from src.models import User
    from src.routers.auth import current_user
    app.dependency_overrides[get_db] = override
    app.dependency_overrides[current_user] = lambda: User(role="member", email="m@eko.co.in")
    try:
        r = TestClient(app).get("/api/v1/system/health")
        assert r.status_code == 200 and r.json()["overall"] in ("ok", "warning", "stopped")
        # A view-only member sees whether it runs, not the error lines.
        assert all(p["errors"] == [] for p in r.json()["parts"])
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(current_user, None)
