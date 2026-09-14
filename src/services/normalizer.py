import re
import urllib.parse
from typing import Optional, Dict, Any

def normalize_text(text: Optional[str]) -> Optional[str]:
    """Clean extra whitespace and return None if empty."""
    if not text:
        return None
    cleaned = re.sub(r'\s+', ' ', str(text)).strip()
    return cleaned if cleaned else None

def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """
    Normalize phone number safely.
    Handles standard Indian phone formats without corrupting non-standard formats.
    """
    if not phone:
        return None
    
    # Strip basic noise like labels
    raw = re.sub(r'^(?:Phone|Tel|Mobile|Call)[:\s]*', '', str(phone), flags=re.IGNORECASE).strip()
    if not raw:
        return None
    
    # Extract digits and leading plus
    has_plus = raw.startswith('+')
    digits = re.sub(r'\D', '', raw)
    
    if not digits:
        return None

    # Handle Indian 10-digit mobile/landline numbers
    # If 12 digits starting with 91, extract the 10 digits
    if len(digits) == 12 and digits.startswith('91'):
        return f"+91{digits[2:]}"
    elif len(digits) == 11 and digits.startswith('0'):
        return f"+91{digits[1:]}"
    elif len(digits) == 10 and digits[0] in '6789':
        return f"+91{digits}"
    elif has_plus:
        return f"+{digits}"
    
    return digits

def normalize_url(url: Optional[str]) -> Optional[str]:
    """
    Normalize website / Google Maps URL by stripping tracking params and trailing slash.
    """
    if not url:
        return None
    
    url = str(url).strip()
    if not url:
        return None
    
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme:
            url = f"https://{url}"
            parsed = urllib.parse.urlparse(url)
        
        # Remove tracking parameters
        if parsed.query:
            query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            filtered_pairs = [
                (k, v) for k, v in query_pairs 
                if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid', 'ref')
            ]
            clean_query = urllib.parse.urlencode(filtered_pairs)
        else:
            clean_query = ""
            
        clean_url = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip('/') if parsed.path != '/' else '/',
            parsed.params,
            clean_query,
            parsed.fragment
        ))
        return clean_url.rstrip('/')
    except Exception:
        return url.strip()

def normalize_address(address: Optional[str]) -> Optional[str]:
    """
    Normalize address by trimming whitespace.
    Preserves all meaningful location parts without over-cleaning.
    """
    if not address:
        return None
    
    # Strip prefixes like "Address: " if present
    raw = re.sub(r'^(?:Address|Loc)[:\s]*', '', str(address), flags=re.IGNORECASE).strip()
    return normalize_text(raw)

def normalize_business_record(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize all fields in an extracted business dictionary.
    """
    return {
        "name": normalize_text(data.get("name")),
        "address": normalize_address(data.get("address")),
        "phone": normalize_phone(data.get("phone")),
        "email": normalize_text(data.get("email")),
        "website": normalize_url(data.get("website")),
        "google_maps_url": normalize_url(data.get("google_maps_url")),
        "place_id": normalize_text(data.get("place_id")),
        "category": normalize_text(data.get("category")),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "officename": normalize_text(data.get("officename")),
        "district": normalize_text(data.get("district")),
        "statename": normalize_text(data.get("statename") or data.get("state"))
    }
