"""
Whether a PIN code someone sent is one we serve.

A PIN is served when it is on our list of target locations, or when it lies
within ONBOARDING_RADIUS_KM (20 km by default) of one that is. The second needs
the PIN's coordinates, which our own list does not have for a PIN that is not
on it, so it is looked up on OpenStreetMap's geocoder.

Only the PIN code is sent to the geocoder, never anything about the person.
"""
import logging
import os
import re
import threading
import time
from functools import lru_cache
from typing import Optional, Tuple

import requests
from sqlalchemy.orm import Session

from src.models.location import Location
from src.services.geo_validator import haversine_distance

logger = logging.getLogger("gmap_scraper.pincode")

RADIUS_KM = float(os.environ.get("ONBOARDING_RADIUS_KM", "20"))

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
INDIA_POST_URL = "https://api.postalpincode.in/pincode/{pin}"
# Nominatim's usage policy asks every client to say who it is.
USER_AGENT = "AutoGMap/1.0 (Eko onboarding PIN check)"

# An Indian PIN: six digits, never starting with 0.
_PIN = re.compile(r"(?<!\d)([1-9]\d{5})(?!\d)")


def extract_pincode(text: Optional[str]) -> Optional[str]:
    """The PIN in what someone typed, allowing "110 001" as well as "110001"."""
    if not text:
        return None
    match = _PIN.search(re.sub(r"(?<=\d)[\s-](?=\d)", "", text))
    return match.group(1) if match else None


# OpenStreetMap's geocoder allows one request a second and answers 429 to
# anything faster. A sync placing several PINs, or the bot and a sync at
# once, would otherwise exceed it.
_MIN_INTERVAL = 1.1
_last_call = 0.0
_pace = threading.Lock()


def _nominatim(params: dict) -> Optional[Tuple[float, float]]:
    global _last_call
    with _pace:
        wait = _last_call + _MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
    resp = requests.get(
        NOMINATIM_URL,
        params={**params, "format": "json", "limit": 1, "countrycodes": "in"},
        headers={"User-Agent": USER_AGENT},
        timeout=8,
    )
    resp.raise_for_status()
    rows = resp.json()
    if rows:
        return float(rows[0]["lat"]), float(rows[0]["lon"])
    return None


@lru_cache(maxsize=2048)
def locate(pin: str) -> Optional[Tuple[float, float]]:
    """
    Coordinates for a PIN code, or None if it cannot be found.

    OpenStreetMap does not know every Indian PIN, so a miss falls back to India
    Post, which names the PIN's post office and district, and that place is
    looked up instead. Only a success is cached: a failure may be a network
    blip, and caching it would refuse the person for as long as the process
    runs.
    """
    try:
        found = _nominatim({"postalcode": pin, "country": "India"})
        if found:
            return found
    except Exception as exc:
        logger.warning(f"pincode event=NOMINATIM_FAILED pin={pin} error={exc}")

    try:
        resp = requests.get(INDIA_POST_URL.format(pin=pin), timeout=8,
                            headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        data = resp.json()
        offices = (data[0] or {}).get("PostOffice") or [] if data else []
        if offices:
            office = offices[0]
            query = ", ".join(p for p in (office.get("Name"), office.get("District"),
                                          office.get("State"), "India") if p)
            found = _nominatim({"q": query})
            if found:
                return found
            # The district alone is coarser, but better than nothing.
            query = ", ".join(p for p in (office.get("District"), office.get("State"), "India") if p)
            found = _nominatim({"q": query})
            if found:
                return found
    except Exception as exc:
        logger.warning(f"pincode event=INDIA_POST_FAILED pin={pin} error={exc}")

    raise LookupError(pin)


def _locate_or_none(pin: str) -> Optional[Tuple[float, float]]:
    try:
        return locate(pin)
    except LookupError:
        return None


def _label(loc: Location) -> str:
    return ", ".join(p for p in (loc.anchor_name or loc.tehsil, loc.district, loc.state) if p)


def check(db: Session, pin: str) -> dict:
    """
    {"status": "served" | "not_served" | "unknown", ...}

    "unknown" means the PIN could not be placed on a map, which is not the
    same as being out of range: the bot asks again rather than turning the
    person away.
    """
    exact = db.query(Location).filter(Location.pincode == pin).first()
    if exact:
        return {"status": "served", "pincode": pin, "nearest_pincode": pin,
                "distance_km": 0.0, "place": _label(exact)}

    coords = _locate_or_none(pin)
    if coords is None:
        return {"status": "unknown", "pincode": pin}

    lat, lng = coords
    best, best_km = None, None
    for loc in db.query(Location).all():
        if loc.latitude is None or loc.longitude is None:
            continue
        km = haversine_distance(lat, lng, loc.latitude, loc.longitude)
        if best_km is None or km < best_km:
            best, best_km = loc, km

    if best is None:
        return {"status": "not_served", "pincode": pin}

    return {
        "status": "served" if best_km <= RADIUS_KM else "not_served",
        "pincode": pin,
        "nearest_pincode": best.pincode,
        "distance_km": round(best_km, 1),
        "place": _label(best),
    }
