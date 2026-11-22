"""
Eko Acquisition's API, as an adapter (Phase 2, 22 Nov 2026: split out of
acquisition_handover, which keeps what is AutoGMap's own: what a lead's hand-over
says). POSTs one JSON body and says whether it went.

Until EKO_ACQUISITION_API_URL (and EKO_ACQUISITION_API_KEY, sent as a Bearer token)
are set, nothing is sent and the caller is told to wait.
"""
import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger("gmap_scraper.acquisition_handover")

TIMEOUT_SECONDS = 20


def configured() -> bool:
    return bool(os.environ.get("EKO_ACQUISITION_API_URL"))


def post(body: dict, ref: str = "") -> Tuple[bool, bool, Optional[str]]:
    """
    Sends `body`. Returns (sent, waiting, why not): waiting when the API is not set
    up yet, did not answer, or failed on its side, so it is worth trying again.
    `ref` names the lead in the logs (its last digits only).
    """
    if not configured():
        return False, True, "Eko Acquisition's API is not set up yet (its address and key are needed)"
    import requests

    url = os.environ["EKO_ACQUISITION_API_URL"]
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("EKO_ACQUISITION_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        r = requests.post(url, json=body, headers=headers, timeout=TIMEOUT_SECONDS)
    except Exception as e:
        logger.warning(f"acquisition_handover event=SEND_FAILED ref={ref} error={e}")
        return False, True, f"Eko Acquisition's API did not answer: {str(e)[:200]}"
    if 200 <= r.status_code < 300:
        logger.info(f"acquisition_handover event=SENT ref={ref} status={r.status_code}")
        return True, False, None
    # A refusal of the lead itself (4xx) will not change by retrying; a server error may.
    waiting = r.status_code >= 500 or r.status_code == 429
    logger.warning(f"acquisition_handover event=REFUSED ref={ref} status={r.status_code}")
    return False, waiting, f"Eko Acquisition's API answered {r.status_code}: {r.text[:200]}"
