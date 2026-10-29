"""
Kiosk KAI, read by the app: what happens to our leads after AutoGMap.

Kiosk KAI (https://indev.eko.in/kiosk-kai/mcp) is one read-only MCP server
over AutoGMap, the Kiosk Application Form, where our leads apply, and TARA,
which runs the CSPs they become. The growth plan, AutoGMap's feedback loop,
reads three things from it:

- autogmap.tara_context: TARA's CSP network and revenue forecasts, live, in
  the keys of data/business_context.json (the 04:30 export stays the fallback);
- autogmap.acquisition_funnel: the form's applications from AutoGMap and
  TARA's CSPs in the states our leads come from;
- ekokiosk.campaign_targets: the districts Eko's targeting sheet says need a
  campaign.

People ask it questions from the Plan tab too, through core.ask (below).

The app signs in as its own Kiosk KAI user, never a person's: calls are
logged under that user, and a person's key must not be in the app, its .env
or its containers. Without KIOSK_KAI_APP_KEY nothing is called and the plan
works as before, from AutoGMap's own data.

No tool returns a person's name, phone, email or message. Answers are kept
for CACHE_MINUTES, so the plan, which is rebuilt often, calls each tool a few
times an hour at most. Any failure is logged and read as "no answer".
"""
import json
import logging
import os
import threading
import time
import uuid
from typing import Optional

import requests

logger = logging.getLogger("gmap_scraper.kiosk_kai")

DEFAULT_URL = "https://indev.eko.in/kiosk-kai/mcp"
PROTOCOL = "2025-06-18"
TIMEOUT = 45
CACHE_MINUTES = 30
# Named in Kiosk KAI's audit log beside the app's user.
SKILL = "autogmap-growth-plan"

_cache: dict = {}


def configured() -> bool:
    return bool(os.environ.get("KIOSK_KAI_APP_KEY"))


def _url() -> str:
    return os.environ.get("KIOSK_KAI_URL") or DEFAULT_URL


def _post(body: dict, session: Optional[str] = None, timeout: int = TIMEOUT):
    headers = {
        "Authorization": f"Bearer {os.environ['KIOSK_KAI_APP_KEY']}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if session:
        headers["Mcp-Session-Id"] = session
    r = requests.post(_url(), json=body, headers=headers, timeout=timeout)
    r.raise_for_status()
    text = r.text or ""
    if "event-stream" in r.headers.get("content-type", ""):
        events = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        text = events[-1] if events else ""
    return r.headers.get("mcp-session-id") or session, (json.loads(text) if text.strip() else None)


def _call(tool: str, arguments: dict, timeout: int = TIMEOUT, skill: str = SKILL) -> Optional[dict]:
    session, init = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "autogmap", "version": "1"}}})
    if not init or "error" in init:
        raise RuntimeError(f"initialize refused: {(init or {}).get('error')}")
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
    _, out = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": tool, "arguments": {**arguments, "skill": skill}}}, session, timeout)
    if not out or "error" in out:
        raise RuntimeError(f"call refused: {(out or {}).get('error')}")
    result = out.get("result") or {}
    content = result.get("content") or []
    body = result.get("structuredContent") or (json.loads(content[0]["text"]) if content else None)
    if result.get("isError") or not isinstance(body, dict) or body.get("error"):
        raise RuntimeError(f"tool error: {str((body or {}).get('error') if isinstance(body, dict) else content)[:200]}")
    return body


def call(tool: str, **arguments) -> Optional[dict]:
    """
    One tool's answer, {"data", "source", "as_of", "caveats", ...}, or None:
    no key, or Kiosk KAI did not answer. Kept for CACHE_MINUTES.
    """
    if not configured():
        return None
    key = (tool, json.dumps(arguments, sort_keys=True))
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    try:
        body = _call(tool, arguments)
    except Exception as e:
        logger.warning(f"kiosk_kai event=CALL_FAILED tool={tool} error={type(e).__name__}: {str(e)[:200]}")
        body = None
    # A failure is kept for a shorter while, so an outage does not slow every plan.
    _cache[key] = (time.monotonic() + (CACHE_MINUTES if body else 5) * 60, body)
    return body


# --- Questions from the Plan tab ----------------------------------------------
#
# Anyone signed in can ask Kiosk KAI's own agent (core.ask) a question in plain
# words: about AutoGMap, the application form, or TARA's CSPs and revenue. It
# answers as the app's user, from the same read-only tools, with each figure's
# system and as-of. An answer takes up to a few minutes, longer than the proxy
# in front of the app waits, so a question runs in a thread and the page asks
# for it every few seconds. Questions live in this process only: the app runs
# one worker, and a question lost to a restart is simply asked again.

ASK_TOOL = "core.ask"
ASK_SKILL = "autogmap-ask-bar"
ASK_TIMEOUT = 300
# Each answer costs money, and the team shares Kiosk KAI's USD 5 a day, so the
# app asks at most this many questions a day (IST), and one at a time each.
ASK_DAILY_DEFAULT = 20
ASK_RUNNING_MAX = 3
ASK_KEEP = 200
CHAT_URL = "https://indev.eko.in/kiosk-kai/chat/"

_asks: dict = {}
_asks_lock = threading.Lock()
_asked_today = {"day": None, "count": 0}


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + 5.5 * 3600))


def ask_daily_max() -> int:
    try:
        return max(0, int(os.environ.get("KIOSK_KAI_ASK_DAILY") or ASK_DAILY_DEFAULT))
    except ValueError:
        return ASK_DAILY_DEFAULT


def asks_left() -> int:
    with _asks_lock:
        used = _asked_today["count"] if _asked_today["day"] == _today() else 0
    return max(0, ask_daily_max() - used)


class AskRefused(Exception):
    """Why a question was not started, in words for the person who asked."""


def _names(tools) -> list:
    out = []
    for t in tools or []:
        name = t if isinstance(t, str) else (t.get("name") or t.get("tool")) if isinstance(t, dict) else None
        if name and name not in out:
            out.append(name)
    return out


def _answer(body: dict) -> dict:
    """core.ask's reply, read leniently: the answer, the tools it used, as-of and caveats."""
    data = body.get("data")
    if isinstance(data, str):
        data = {"answer": data}
    data = data if isinstance(data, dict) else {}
    text = data.get("answer") or data.get("text") or body.get("answer") or ""
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("no answer in the reply")
    cost = data.get("cost_usd", data.get("cost"))
    return {
        "answer": text.strip(),
        "tools": _names(data.get("tools_called") or data.get("tools") or body.get("tools_called")),
        "as_of": body.get("as_of") or data.get("as_of"),
        "caveats": [c for c in (body.get("caveats") or data.get("caveats") or []) if isinstance(c, str)],
        "cost": cost if isinstance(cost, (int, float)) else None,
    }


def _run_ask(ask_id: str, question: str) -> None:
    try:
        result = _answer(_call(ASK_TOOL, {"question": question}, ASK_TIMEOUT, ASK_SKILL))
        update = {"status": "done", **result}
    except Exception as e:
        logger.warning(f"kiosk_kai event=ASK_FAILED id={ask_id} error={type(e).__name__}: {str(e)[:200]}")
        update = {"status": "failed",
                  "error": "Kiosk KAI did not answer this time. Try again in a minute, or ask it more simply."}
    with _asks_lock:
        if ask_id in _asks:
            _asks[ask_id].update(update, finished=time.time())


def ask(question: str, user_id: str) -> dict:
    """Starts a question; its id and state. Raises AskRefused when it cannot start."""
    if not configured():
        raise AskRefused("Asking needs the app's own Kiosk KAI key on the server (KIOSK_KAI_APP_KEY).")
    with _asks_lock:
        running = [a for a in _asks.values() if a["status"] == "running"]
        if any(a["user_id"] == user_id for a in running):
            raise AskRefused("Your last question is still being answered. Wait for it, then ask the next.")
        if len(running) >= ASK_RUNNING_MAX:
            raise AskRefused("Kiosk KAI is answering others right now. Try again in a minute.")
        if _asked_today["day"] != _today():
            _asked_today.update(day=_today(), count=0)
        if _asked_today["count"] >= ask_daily_max():
            raise AskRefused(f"Today's {ask_daily_max()} questions have been asked; Kiosk KAI's budget is shared. "
                             "Ask again tomorrow, or use the full chat.")
        _asked_today["count"] += 1
        ask_id = uuid.uuid4().hex[:16]
        _asks[ask_id] = {"id": ask_id, "user_id": user_id, "question": question,
                         "status": "running", "started": time.time()}
        for old in sorted(_asks, key=lambda k: _asks[k]["started"])[:max(0, len(_asks) - ASK_KEEP)]:
            if _asks[old]["status"] != "running":
                del _asks[old]
    # The question itself is not logged: it may name a person.
    logger.info(f"kiosk_kai event=ASK id={ask_id} user={user_id} chars={len(question)}")
    threading.Thread(target=_run_ask, args=(ask_id, question), daemon=True, name=f"kai-ask-{ask_id}").start()
    return asked(ask_id, user_id)


def asked(ask_id: str, user_id: str) -> Optional[dict]:
    """A question's state, only for the person who asked it."""
    with _asks_lock:
        a = _asks.get(ask_id)
        if not a or a["user_id"] != user_id:
            return None
        out = {k: v for k, v in a.items() if k not in ("user_id", "finished")}
    out["seconds"] = round((a.get("finished") or time.time()) - a["started"])
    return out
