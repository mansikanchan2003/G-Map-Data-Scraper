import math
import re
from typing import Optional, Tuple, List

EARTH_RADIUS_KM = 6371.0

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on the Earth
    using the Haversine formula. Returns distance in kilometers.
    """
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return EARTH_RADIUS_KM * c

def is_valid_coordinate(lat: Optional[float], lng: Optional[float]) -> bool:
    """Check if lat and lng are valid numeric coordinates within geographical bounds."""
    if lat is None or lng is None:
        return False
    try:
        lat_f = float(lat)
        lng_f = float(lng)
        if math.isnan(lat_f) or math.isinf(lat_f) or math.isnan(lng_f) or math.isinf(lng_f):
            return False
        return -90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0
    except (ValueError, TypeError):
        return False

def extract_coords_from_url(url: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """
    Attempt to extract (latitude, longitude) from Google Maps URLs.
    Supports formats:
    - ...!3d28.6139!4d77.2090...
    - .../@28.6139,77.2090...
    - ...?q=28.6139,77.2090...
    """
    if not url:
        return None, None
        
    # Pattern 1: !3d<lat>!4d<lng>
    match_3d4d = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
    if match_3d4d:
        try:
            return float(match_3d4d.group(1)), float(match_3d4d.group(2))
        except ValueError:
            pass

    # Pattern 2: /@<lat>,<lng>
    match_at = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match_at:
        try:
            return float(match_at.group(1)), float(match_at.group(2))
        except ValueError:
            pass

    # Pattern 3: ?q=<lat>,<lng>
    match_q = re.search(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if match_q:
        try:
            return float(match_q.group(1)), float(match_q.group(2))
        except ValueError:
            pass

    return None, None

def validate_geo_distance(
    business_lat: Optional[float],
    business_lng: Optional[float],
    target_lat: float,
    target_lng: float,
    radius_km: float = 20.0
) -> Tuple[bool, Optional[float], List[str]]:
    """
    Strict geographic validation against the target search coordinates:
    1. If coordinates are missing: fails validation (cannot assume inside radius).
    2. If coordinates are invalid: fails validation.
    3. If coordinates are present & valid: validates distance <= radius_km.
    
    Returns:
    - is_valid (bool)
    - distance_km (float or None)
    - errors / notes (List[str])
    """
    notes = []
    
    # 1. Missing coordinates check: DO NOT assume inside radius
    if business_lat is None or business_lng is None:
        notes.append("COORDINATES_UNAVAILABLE: Listing did not provide extractable latitude/longitude; geographic validation unresolved/failed.")
        return False, None, notes

    # 2. Invalid coordinate range check
    if not is_valid_coordinate(business_lat, business_lng) or not is_valid_coordinate(target_lat, target_lng):
        notes.append("INVALID_COORDINATES: Coordinates are invalid or outside geographic bounds [-90..90, -180..180].")
        return False, None, notes

    # 3. Calculate Haversine distance
    distance = haversine_distance(target_lat, target_lng, business_lat, business_lng)
    rounded_distance = round(distance, 2)
    
    # 4. Strict boundary check (<= radius_km)
    if distance <= radius_km:
        return True, rounded_distance, notes
    else:
        notes.append(f"DISTANCE_EXCEEDED: Distance {rounded_distance}km exceeds allowed radius {radius_km:.2f}km.")
        return False, rounded_distance, notes
