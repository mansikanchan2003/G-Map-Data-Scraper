"""
A sanity check on coordinates that were looked up rather than supplied.

A bare PIN code is ambiguous to Google Maps. Searching "385002" returned a
point in the Caucasus; three Kheda codes resolved to Lucknow. Those rows look
perfectly normal in the database — the right district and state beside
coordinates a thousand kilometres away — and every business discovered under
them inherits the wrong geography. By the time that shows up it looks like a
scraping fault, not a geocoding one.

So a resolved point is checked against the state it is claimed to be in. The
rectangles are deliberately generous: they exist to catch another state or
another country, not to trace a border.
"""
from typing import Optional

# (min_lat, max_lat, min_lon, max_lon)
STATE_BOUNDS = {
    "andhra pradesh": (12.6, 19.9, 76.7, 84.8),
    "assam": (24.1, 28.0, 89.7, 96.1),
    "bihar": (24.2, 27.6, 83.3, 88.3),
    "chhattisgarh": (17.7, 24.2, 80.2, 84.5),
    "delhi": (28.4, 28.9, 76.8, 77.4),
    "goa": (14.8, 15.9, 73.6, 74.4),
    "gujarat": (20.0, 24.8, 68.0, 74.6),
    "haryana": (27.6, 30.9, 74.4, 77.7),
    "himachal pradesh": (30.3, 33.3, 75.5, 79.1),
    "jharkhand": (21.9, 25.4, 83.3, 87.99),
    "karnataka": (11.5, 18.5, 74.0, 78.6),
    "kerala": (8.1, 12.8, 74.8, 77.5),
    "madhya pradesh": (21.0, 26.9, 74.0, 82.9),
    "maharashtra": (15.6, 22.1, 72.6, 80.9),
    "odisha": (17.7, 22.6, 81.3, 87.6),
    "punjab": (29.5, 32.6, 73.8, 76.99),
    "rajasthan": (23.0, 30.2, 69.4, 78.3),
    "tamil nadu": (8.0, 13.6, 76.2, 80.4),
    "telangana": (15.8, 19.95, 77.2, 81.4),
    "uttar pradesh": (23.8, 30.5, 77.0, 84.7),
    "uttarakhand": (28.7, 31.5, 77.5, 81.1),
    "west bengal": (21.4, 27.3, 85.8, 89.9),
}

# Everything in the country, for a state that is not listed above.
INDIA_BOUNDS = (6.5, 35.7, 68.0, 97.5)


def check(state: Optional[str], latitude: Optional[float],
          longitude: Optional[float]) -> Optional[str]:
    """
    Returns a reason the point looks wrong, or None when it is plausible.

    An unlisted state falls back to the country, so a result abroad is still
    caught. Missing coordinates are somebody else's error to report.
    """
    if latitude is None or longitude is None:
        return None

    lo_lat, hi_lat, lo_lon, hi_lon = INDIA_BOUNDS
    if not (lo_lat <= latitude <= hi_lat and lo_lon <= longitude <= hi_lon):
        return (f"{latitude}, {longitude} is outside India. "
                f"The search matched somewhere else entirely.")

    box = STATE_BOUNDS.get((state or "").strip().lower())
    if box is None:
        return None

    lo_lat, hi_lat, lo_lon, hi_lon = box
    if lo_lat <= latitude <= hi_lat and lo_lon <= longitude <= hi_lon:
        return None

    return (f"{latitude}, {longitude} is not in {state}. "
            f"A PIN code on its own is ambiguous to Maps; add the town or "
            f"district as the anchor name, or enter the coordinates directly.")
