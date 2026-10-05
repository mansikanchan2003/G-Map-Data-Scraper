"""
Whether this machine can reach the internet at all.

Discovery cannot tell a dead connection from a search that found nothing: on
3 October 2026 the server's link went down and the autopilot ran its thirty
batches a day into it for two days, failing 1,490 jobs one name-lookup error
at a time. A check that costs a second answers the question before a browser
is ever started.
"""
import logging
import socket

logger = logging.getLogger("gmap_scraper.connectivity")

# Somewhere that is always up. Maps itself, since that is what is needed.
PROBE_HOST = "www.google.com"
PROBE_PORT = 443
TIMEOUT_SECONDS = 5

# What a browser reports when the connection, not the page, is the problem.
NETWORK_ERROR_MARKERS = (
    "ERR_NAME_NOT_RESOLVED",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_NETWORK_CHANGED",
    "ERR_ADDRESS_UNREACHABLE",
    "ERR_NETWORK_ACCESS_DENIED",
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_CONNECTION_REFUSED",
    "ERR_CONNECTION_RESET",
    "ERR_PROXY_CONNECTION_FAILED",
    "ERR_TIMED_OUT",
)


def is_online() -> bool:
    """True when a name can be looked up and a connection opened to it."""
    try:
        with socket.create_connection((PROBE_HOST, PROBE_PORT), timeout=TIMEOUT_SECONDS):
            return True
    except OSError as e:
        logger.warning(f"connectivity event=OFFLINE reason={e}")
        return False


def looks_like_network_failure(error) -> bool:
    """Whether a job's error reads as the connection failing, not the search."""
    text = str(error or "")
    return any(marker in text for marker in NETWORK_ERROR_MARKERS)
