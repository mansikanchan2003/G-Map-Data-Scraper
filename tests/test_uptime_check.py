"""
The uptime check (scripts/uptime_check.py): one email when the site goes
down, a reminder every few hours while it stays down, one when it is back.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
import requests

from scripts import uptime_check as u

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


class Answer:
    def __init__(self, status=200, body=None, json_type=True):
        self.status_code = status
        self._body = body if body is not None else {"status": "healthy"}
        self.headers = {"content-type": "application/json" if json_type else "text/html"}

    def json(self):
        if not self.headers["content-type"].startswith("application/json"):
            raise ValueError("not json")
        return self._body


def test_healthy_is_up_and_a_refusal_is_down_after_retries(monkeypatch):
    monkeypatch.setattr(u.requests, "get", lambda url, timeout: Answer())
    assert u.check("https://x/health", wait=0) == (True, "healthy")

    calls = []

    def refused(url, timeout):
        calls.append(url)
        raise requests.ConnectionError("Connection refused")
    monkeypatch.setattr(u.requests, "get", refused)
    up, seen = u.check("https://x/health", wait=0)
    assert not up and "Connection refused" in seen and len(calls) == u.TRIES

    # The database down: the API answers 200 but says unhealthy.
    monkeypatch.setattr(u.requests, "get", lambda url, timeout: Answer(body={"status": "unhealthy"}))
    assert u.check("https://x/health", wait=0) == (False, "HTTP 200, status unhealthy")


def test_one_email_down_reminders_while_down_and_one_when_back():
    state, email = u.decide({}, False, "ConnectionError", NOW)
    assert email[0] == "AutoGMap is down" and "ConnectionError" in email[1]

    # Five minutes on, still down: no second email.
    state, email = u.decide(state, False, "ConnectionError", NOW + timedelta(minutes=5))
    assert email is None and state["down_since"] == NOW.isoformat()

    # Two hours on: a reminder, with how long.
    state, email = u.decide(state, False, "ConnectionError", NOW + timedelta(hours=2, minutes=1))
    assert email[0] == "AutoGMap is still down (2 h 1 min)"

    state, email = u.decide(state, True, "healthy", NOW + timedelta(hours=3))
    assert email[0] == "AutoGMap is back up" and "3 h 0 min" in email[1]
    assert state["up"] is True

    # Up and up: nothing.
    assert u.decide(state, True, "healthy", NOW + timedelta(hours=4))[1] is None


def test_the_state_is_kept_only_when_it_changes(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setattr(u, "check", lambda url: (True, "healthy"))
    state = tmp_path / "state.json"
    u.main(["--url", "https://x/health", "--state", str(state)])
    assert json.loads(state.read_text())["up"] is True
    u.main(["--url", "https://x/health", "--state", str(state)])
    assert out.read_text().splitlines()[-1] == "changed=false"

    monkeypatch.setattr(u, "check", lambda url: (False, "Timeout"))
    u.main(["--url", "https://x/health", "--state", str(state)])
    assert out.read_text().splitlines()[-1] == "changed=true"
    assert json.loads(state.read_text())["up"] is False
