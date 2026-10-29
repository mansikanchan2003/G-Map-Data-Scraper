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
import time
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


def _post(body: dict, session: Optional[str] = None):
    headers = {
        "Authorization": f"Bearer {os.environ['KIOSK_KAI_APP_KEY']}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if session:
        headers["Mcp-Session-Id"] = session
    r = requests.post(_url(), json=body, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    text = r.text or ""
    if "event-stream" in r.headers.get("content-type", ""):
        events = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        text = events[-1] if events else ""
    return r.headers.get("mcp-session-id") or session, (json.loads(text) if text.strip() else None)


def _call(tool: str, arguments: dict) -> Optional[dict]:
    session, init = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "autogmap", "version": "1"}}})
    if not init or "error" in init:
        raise RuntimeError(f"initialize refused: {(init or {}).get('error')}")
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
    _, out = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": tool, "arguments": {**arguments, "skill": SKILL}}}, session)
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
