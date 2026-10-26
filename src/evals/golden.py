"""
The golden evaluation set (the team's blueprint, phase 2, 2026-10-26): real
lead messages and drafts with the answer AutoGMap must give, run before every
deploy so a change to the bot or a checker cannot quietly break it.

Each case runs on its own in-memory database with WhatsApp, the geocoder, Drive
and email replaced by stand-ins: nothing is sent, nothing leaves the machine,
and the real database is never touched. Suites:

- bot_flow: the onboarding steps (language, PIN, education, investment, documents).
- faq: a question answered from Eko's confirmed FAQ, in the lead's words.
- reply_disposition: a reply read as its disposition, and replies that must not be.
- trust: a doubt about Eko answered, and recorded as a trust concern.
- copy_check: drafts the copy checker must pass or stop.

Run: python -m src.evals.golden [--suite NAME] [--save]
--save keeps the report in the real database for the Agent quality page.
Exits 1 when any case fails, so a deploy can stop on it.
"""
import argparse
import contextlib
import itertools
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

CASES_FILE = os.path.join(os.path.dirname(__file__), "golden_cases.json")
SETTING_KEY = "golden_eval"
PHONE = "+919000000001"
SERVED_PIN = "110001"
# Where the stand-in geocoder places a PIN: in our area, far from it, or nowhere.
PLACES = {"110001": (28.6328, 77.2197), "110017": (28.55, 77.25), "400001": (19.07, 72.87), "380001": (23.02, 72.57)}


def load_cases(suite: Optional[str] = None) -> List[dict]:
    with open(CASES_FILE, encoding="utf-8") as fh:
        cases = json.load(fh)["cases"]
    return [c for c in cases if not suite or c["suite"] == suite]


class _Meta:
    """WhatsApp, as far as the bot can tell: every send succeeds and is kept."""
    sent: List[tuple] = []
    _n = itertools.count()

    def _ok(self):
        return True, f"wamid.golden{next(self._n)}", "200", None, None

    def send_text_message(self, to, body):
        _Meta.sent.append(("text", body)); return self._ok()

    def send_button_message(self, to, body, buttons):
        _Meta.sent.append(("buttons", body)); return self._ok()

    def send_link_message(self, to, body, text, url):
        _Meta.sent.append(("link", body)); return self._ok()

    def send_template_message(self, to, name, language="en_US", components=None):
        _Meta.sent.append(("template", name)); return self._ok()

    def send_media_message(self, to, kind, media_id, caption=None, filename=None):
        _Meta.sent.append((kind, caption)); return self._ok()

    def upload_media(self, path, kind):
        return "media.golden"

    def download_media(self, media_id):
        return None, None, "Not in the golden run"


@contextlib.contextmanager
def _stand_ins() -> Iterator[None]:
    """Swap the outside world for stand-ins, and put everything back afterwards."""
    from src.services import drive_uploads, inbox, notifier, onboarding_bot, pincode_coverage
    saved = []

    def swap(obj, name, value):
        saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    swap(inbox, "MetaWhatsAppService", _Meta)
    swap(pincode_coverage, "_locate_or_none", lambda pin: PLACES.get(pin))
    swap(drive_uploads, "save_in_background", lambda phone: None)
    swap(notifier, "_send", lambda to, subject, body: True)
    swap(onboarding_bot, "GUIDANCE_TODAY_UNTIL", 0)
    os.environ.setdefault("PUBLIC_BASE_URL", "https://golden.example.in")
    try:
        yield
    finally:
        for obj, name, value in reversed(saved):
            setattr(obj, name, value)


def _fresh_db():
    import src.models  # noqa: F401  (registers every table)
    from src.database import Base
    from src.models import Location, WhatsAppCampaign, WhatsAppCampaignRecipient

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    db.add(Location(location_id=uuid.uuid4().hex[:12], pincode=SERVED_PIN, latitude=28.6328, longitude=77.2197,
                    district="New Delhi", state="Delhi"))
    cid = uuid.uuid4().hex
    db.add(WhatsAppCampaign(campaign_id=cid, name="Golden CSP", data_source_type="scraped", status="COMPLETED",
                            total_contacts=50))
    db.add(WhatsAppCampaignRecipient(recipient_id=uuid.uuid4().hex, campaign_id=cid, phone=PHONE, status="READ",
                                     provider_message_id="wamid.golden.campaign"))
    db.commit()
    return db


_seq = itertools.count()


def _inbound(db, kind: str, **fields) -> None:
    from src.models.inbox import WhatsAppConversation
    from src.services import inbox, onboarding_bot
    message = {"from": PHONE.lstrip("+"), "id": f"wamid.goldenin{next(_seq)}",
               "timestamp": str(int(inbox.now().timestamp())), "type": kind, **fields}
    msg = inbox.record_inbound(db, message, "Golden Lead")
    db.commit()
    if msg is not None:
        conv = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == PHONE).one()
        onboarding_bot.handle(db, conv, msg)
        db.commit()


def _step(db, step: dict) -> None:
    from src.models.inbox import WhatsAppConversation
    from src.services import onboarding_bot
    if "tap_campaign" in step:
        _inbound(db, "button", button={"text": "Interested?", "payload": "Interested?"})
        c = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == PHONE).first()
        if step["tap_campaign"] and c is not None and c.bot_step == onboarding_bot.CHOOSE_LANG:
            _step(db, {"tap": f"lang:{step['tap_campaign']}"})
    elif "tap" in step:
        _inbound(db, "interactive", interactive={"type": "button_reply",
                                                  "button_reply": {"id": step["tap"], "title": step["tap"]}})
    elif "say" in step:
        _inbound(db, "text", text={"body": step["say"]})
    else:
        raise ValueError(f"Unknown step: {step}")


def _check_bot(case: dict) -> List[str]:
    """Run the case's messages through the bot; what differs from the expectation, in words."""
    from src.models.inbox import WhatsAppConversation
    from src.services.bot_messages import HINGLISH, MESSAGES

    db = _fresh_db()
    try:
        _Meta.sent = []
        for step in case["steps"]:
            _step(db, step)
        conv = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == PHONE).first()
        db.refresh(conv)
        reply = _Meta.sent[-1][1] if _Meta.sent else ""
        e, problems = case["expect"], []
        if "bot_step" in e and conv.bot_step != e["bot_step"]:
            problems.append(f"bot step {conv.bot_step!r}, expected {e['bot_step']!r}")
        if "disposition" in e and conv.disposition != e["disposition"]:
            problems.append(f"disposition {conv.disposition!r}, expected {e['disposition']!r}")
        if "data" in e:
            for k, v in e["data"].items():
                got = (conv.bot_data or {}).get(k)
                if got != v:
                    problems.append(f"{k} {got!r}, expected {v!r}")
        if "flagged" in e and bool(conv.needs_attention) != e["flagged"]:
            problems.append(f"needs a person: {bool(conv.needs_attention)}, expected {e['flagged']}")
        for text in e.get("reply_contains", []):
            if text not in reply:
                problems.append(f"reply lacks {text!r}: {reply[:120]!r}")
        if "reply_key" in e:
            lang = e.get("lang", "en")
            table = HINGLISH if lang == "hinglish" else MESSAGES[lang]
            head = table[e["reply_key"]].split("{")[0].strip()[:60]
            if head not in reply:
                problems.append(f"reply is not {e['reply_key']} ({lang}): {reply[:120]!r}")
        return problems
    finally:
        db.close()


def _check_faq(case: dict) -> List[str]:
    from src.services import eko_knowledge
    found = eko_knowledge.match(case["text"])
    problems = [f"{want!r} not matched (got {found})" for want in case["expect"]["faq"] if want not in found]
    if case["expect"].get("only") and set(found) != set(case["expect"]["faq"]):
        problems.append(f"matched {found}, expected only {case['expect']['faq']}")
    return problems


def _variant(case: dict) -> dict:
    """The case's draft: a known-good base with the case's changes ("poster.benefits" reaches inside)."""
    import copy
    with open(CASES_FILE, encoding="utf-8") as fh:
        v = copy.deepcopy(json.load(fh)["bases"][case["base"]]) if case.get("base") else {}
    for path, value in (case.get("set") or {}).items():
        *parents, last = path.split(".")
        node = v
        for p in parents:
            node = node.setdefault(p, {})
        node[last] = value
    return v


def _check_copy(case: dict) -> List[str]:
    from src.services import template_studio
    found = template_studio.validate_copy(case.get("variant") or _variant(case), case["language"])
    e = case["expect"]
    if e.get("clean") and found:
        return [f"the checker stopped a good draft: {found}"]
    missing = [w for w in e.get("problems_mention", []) if not any(w.lower() in p.lower() for p in found)]
    return [f"the checker missed {w!r} (found {found})" for w in missing]


CHECKERS = {"bot_flow": _check_bot, "reply_disposition": _check_bot, "trust": _check_bot, "faq": _check_faq,
            "copy_check": _check_copy}


def run(suite: Optional[str] = None) -> dict:
    """Every case; a report with the pass rate per suite and each failure."""
    cases = load_cases(suite)
    started = time.time()
    results = []
    with _stand_ins():
        for c in cases:
            try:
                problems = CHECKERS[c["suite"]](c)
            except Exception as e:  # a crash is a failure, with its reason
                problems = [f"crashed: {type(e).__name__}: {e}"]
            results.append({"id": c["id"], "suite": c["suite"], "title": c["title"], "passed": not problems,
                            "problems": problems})
    suites: Dict[str, dict] = {}
    for r in results:
        s = suites.setdefault(r["suite"], {"total": 0, "passed": 0})
        s["total"] += 1
        s["passed"] += r["passed"]
    return {"ran_at": datetime.now(timezone.utc).isoformat(), "seconds": round(time.time() - started, 1),
            "total": len(results), "passed": sum(r["passed"] for r in results), "suites": suites,
            "failures": [r for r in results if not r["passed"]]}


def save(report: dict) -> None:
    """Keep the report (and the last 30) in the real database, for the Agent quality page."""
    from src.database import SessionLocal
    from src.models.app_setting import AppSetting
    db = SessionLocal()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
        old = json.loads(row.value) if row and row.value else {}
        history = ([{k: old["last"][k] for k in ("ran_at", "total", "passed")}] if old.get("last") else []) + old.get("history", [])
        value = json.dumps({"last": report, "history": history[:30]})
        if row is None:
            db.add(AppSetting(key=SETTING_KEY, value=value))
        else:
            row.value = value
        db.commit()
    finally:
        db.close()


def latest(db) -> Optional[dict]:
    from src.models.app_setting import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_KEY).first()
    return json.loads(row.value) if row and row.value else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run AutoGMap's golden evaluation set.")
    ap.add_argument("--suite", choices=sorted(CHECKERS))
    ap.add_argument("--save", action="store_true", help="keep the report for the Agent quality page")
    args = ap.parse_args(argv)
    import logging
    logging.disable(logging.CRITICAL)
    report = run(args.suite)
    for name, s in sorted(report["suites"].items()):
        print(f"  {name:<18} {s['passed']:>3}/{s['total']:<3}")
    for f in report["failures"]:
        print(f"FAIL {f['id']} ({f['suite']}): {f['title']}")
        for p in f["problems"]:
            print(f"     - {p}")
    print(f"golden: {report['passed']}/{report['total']} passed in {report['seconds']} s")
    if args.save:
        save(report)
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
