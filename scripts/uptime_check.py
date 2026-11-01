"""
Is AutoGMap up? Run from outside the server (the GitHub workflow
.github/workflows/uptime.yml, every 5 minutes), because a server that is down
cannot say so itself (the outage of 1 Nov 2026 went unnoticed).

It asks the public /health a few times before deciding it is down, so one slow
answer does not wake anyone. It remembers the last state in a small JSON file
(the workflow keeps it between runs) and emails:
- once when the site goes down, with what failed;
- again every REMIND_HOURS while it stays down;
- once when it is back, with how long it was down.

  python scripts/uptime_check.py --url https://indev.eko.in/autogmap/health --state uptime_state.json

Email settings come from the environment, as the app's own: SMTP_HOST,
SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, and ALERT_TO (who is told).
Without them it still checks and prints, and the workflow's run shows it.
"""
import argparse
import json
import os
import smtplib
import sys
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional, Tuple

import requests

TRIES = 3
WAIT_SECONDS = 20
TIMEOUT = 20
REMIND_HOURS = 2


def check(url: str, tries: int = TRIES, wait: float = WAIT_SECONDS) -> Tuple[bool, str]:
    """(up, what was seen). Up means /health answered and said the database is healthy."""
    seen = ""
    for attempt in range(tries):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code == 200 and (r.json() or {}).get("status") == "healthy":
                return True, "healthy"
            seen = f"HTTP {r.status_code}" + (f", status {(r.json() or {}).get('status')}"
                                              if r.headers.get("content-type", "").startswith("application/json") else "")
        except requests.RequestException as e:
            seen = type(e).__name__ + (f": {str(e)[:160]}" if str(e) else "")
        except ValueError:
            seen = "Not a health answer (the page did not return JSON)"
        if attempt < tries - 1:
            time.sleep(wait)
    return False, seen


def _when(iso: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(iso) if iso else None
    except ValueError:
        return None


def _ist(t: datetime) -> str:
    return (t + timedelta(hours=5, minutes=30)).strftime("%d %b %Y, %I:%M %p IST")


def _for(d: timedelta) -> str:
    minutes = int(d.total_seconds() // 60)
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{minutes} min"


def decide(state: dict, up: bool, seen: str, now: datetime) -> Tuple[dict, Optional[Tuple[str, str]]]:
    """The new state, and the email to send (subject, body) if any."""
    was_up = state.get("up", True)
    if up:
        if was_up:
            return {"up": True, "checked_at": now.isoformat()}, None
        since = _when(state.get("down_since")) or now
        return {"up": True, "checked_at": now.isoformat()}, (
            "AutoGMap is back up",
            f"AutoGMap answered again at {_ist(now)}, after being down for about {_for(now - since)} "
            f"(since {_ist(since)}).\n\nThe scraping autopilot resumes by itself. Check the Inbox for WhatsApp "
            f"messages that arrived meanwhile: Meta retries for a while, then gives up.")
    since = _when(state.get("down_since")) if not was_up else now
    since = since or now
    last_alert = _when(state.get("alerted_at"))
    new = {"up": False, "down_since": since.isoformat(), "seen": seen, "checked_at": now.isoformat(),
           "alerted_at": state.get("alerted_at")}
    if was_up or not last_alert or now - last_alert >= timedelta(hours=REMIND_HOURS):
        new["alerted_at"] = now.isoformat()
        first = was_up
        return new, (
            "AutoGMap is down" if first else f"AutoGMap is still down ({_for(now - since)})",
            f"AutoGMap's health check has not answered since {_ist(since)}.\n\nWhat was seen: {seen}\n\n"
            f"While it is down the website, the WhatsApp bot, the document upload page and campaigns do not work. "
            f"Check that the server is on and reachable (SSH on port 2222, the website on 443), and "
            f"`docker compose ps` on it.\n\n"
            + ("" if first else f"You will be told again every {REMIND_HOURS} hours until it is back.\n"))
    return new, None


def send(subject: str, body: str) -> bool:
    host, sender, to = os.environ.get("SMTP_HOST"), os.environ.get("SMTP_FROM"), os.environ.get("ALERT_TO")
    if not (host and sender and to):
        print("uptime: email not set up (SMTP_HOST, SMTP_FROM, ALERT_TO); not sent")
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, sender, to
    msg.set_content(body)
    port = int(os.environ.get("SMTP_PORT", "587"))
    user, password = os.environ.get("SMTP_USER"), (os.environ.get("SMTP_PASSWORD") or "").replace(" ", "") or None
    server = smtplib.SMTP_SSL(host, port, timeout=20) if port == 465 else smtplib.SMTP(host, port, timeout=20)
    try:
        if port != 465:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)
    finally:
        server.quit()
    print(f"uptime: emailed {to}: {subject}")
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", required=True)
    ap.add_argument("--state", default="uptime_state.json")
    args = ap.parse_args(argv)
    try:
        with open(args.state, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        state = {}
    up, seen = check(args.url)
    now = datetime.now(timezone.utc)
    new, email = decide(state, up, seen, now)
    print(f"uptime: {'UP' if up else 'DOWN'} ({seen})")
    if email:
        try:
            sent = send(*email)
        except Exception as e:
            print(f"uptime: email failed: {type(e).__name__}: {e}")
            sent = False
        if not sent:
            # The alert did not go (failed, or email not set up yet): the next run tries again.
            if up:
                new = {**state, "checked_at": now.isoformat()}
            else:
                new["alerted_at"] = state.get("alerted_at")
    with open(args.state, "w", encoding="utf-8") as fh:
        json.dump(new, fh)
    # Kept only when something but the check time changed, so the cache does not fill with copies.
    changed = {k: v for k, v in new.items() if k != "checked_at"} != {k: v for k, v in state.items() if k != "checked_at"}
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"changed={'true' if changed else 'false'}\n")
    # The job stays green either way: GitHub's own failure emails would repeat every 5 minutes.
    return 0


if __name__ == "__main__":
    sys.exit(main())
