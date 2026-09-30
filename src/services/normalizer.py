import logging
import re
import urllib.parse
from typing import Optional, Dict, Any

def normalize_text(text: Optional[str]) -> Optional[str]:
    """Clean extra whitespace and return None if empty."""
    if not text:
        return None
    cleaned = re.sub(r'\s+', ' ', str(text)).strip()
    return cleaned if cleaned else None

logger = logging.getLogger("gmap_scraper.normalizer")


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """
    Return an Indian number as +91 followed by its ten national digits, or None.

    Anything that cannot be expressed that way is dropped rather than stored
    in whatever shape it arrived in. Storing it meant campaigns carried
    numbers nobody could be reached on:

      * Toll-free helplines — 1800…, 1860… — are eleven digits and belong to
        the bank whose branch was listed, not to the business. The same
        handful repeated across hundreds of listings.
      * Border searches return listings from across it. A Gurdaspur radius
        reaches Narowal, Pakistan; those are real businesses but not ones
        this project can contact.
      * Fragments too short or too long to dial at all.

    A valid national number is ten digits and does not begin with 0. Mobiles
    start 6-9; landlines carry an STD code, and plenty of those begin with 1 —
    0181 Jalandhar, 0183 Amritsar, 0172 Chandigarh, 011 Delhi — so a rule that
    barred a leading 1 would have thrown away the landlines of exactly the
    districts being scraped. The toll-free ranges are excluded by length
    instead: 1800… and 1860… are eleven digits, not ten.
    """
    if not phone:
        return None

    raw = re.sub(r'^(?:Phone|Tel|Mobile|Call)[:\s]*', '', str(phone), flags=re.IGNORECASE).strip()
    if not raw:
        return None

    digits = re.sub(r'\D', '', raw)
    if not digits:
        return None

    # Reduce to the ten national digits, whatever the caller wrote around them.
    if len(digits) == 12 and digits.startswith('91'):
        national = digits[2:]
    elif len(digits) == 13 and digits.startswith('091'):
        national = digits[3:]
    elif len(digits) == 11 and digits.startswith('0'):
        national = digits[1:]
    elif len(digits) == 10:
        national = digits
    elif digits.startswith('91') and len(digits) > 12:
        # Two numbers run together, or a number with an extension. Neither is
        # safe to guess at.
        logger.debug("normalizer event=PHONE_TOO_LONG")
        return None
    elif not digits.startswith('91') and (raw.startswith('+') or len(digits) > 12):
        logger.debug(f"normalizer event=FOREIGN_NUMBER_DROPPED prefix={digits[:3]}")
        return None
    else:
        # Eight-digit toll-free stubs, truncated fragments, anything else.
        logger.debug(f"normalizer event=PHONE_UNUSABLE len={len(digits)}")
        return None

    if len(national) != 10 or national[0] == '0':
        logger.debug(f"normalizer event=PHONE_NOT_INDIAN first={national[:1]} len={len(national)}")
        return None

    return f"+91{national}"


def is_mobile(phone: Optional[str]) -> bool:
    """
    True for a number that can receive WhatsApp or SMS.

    Indian mobile numbers begin 6-9; a landline reaches nobody on either
    channel, so a campaign audience is built from these.
    """
    return bool(phone and re.fullmatch(r'\+91[6-9]\d{9}', phone))


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

# Column widths in the businesses table. Scraped values have no length limit
# of their own -- a long Maps listing name or a URL full of query parameters
# can exceed them. Since businesses are inserted in one transaction per job, a
# single oversized value used to abort the insert and discard every business
# that job had found, so values are clamped to fit instead.
FIELD_LIMITS = {
    "name": 500,
    "email": 200,
    "website": 500,
    "place_id": 100,
    "category": 200,
    "officename": 100,
    "district": 100,
    "statename": 100,
}


def clamp(value: Optional[str], limit: int) -> Optional[str]:
    """Trim a value to the width its column allows."""
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[:limit]


def normalize_business_record(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize all fields in an extracted business dictionary.
    """
    return {
        "name": clamp(normalize_text(data.get("name")), FIELD_LIMITS["name"]),
        "address": normalize_address(data.get("address")),
        "phone": normalize_phone(data.get("phone")),
        "email": clamp(normalize_text(data.get("email")), FIELD_LIMITS["email"]),
        "website": clamp(normalize_url(data.get("website")), FIELD_LIMITS["website"]),
        "google_maps_url": normalize_url(data.get("google_maps_url")),
        "place_id": clamp(normalize_text(data.get("place_id")), FIELD_LIMITS["place_id"]),
        "category": clamp(normalize_text(data.get("category")), FIELD_LIMITS["category"]),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "officename": clamp(normalize_text(data.get("officename")), FIELD_LIMITS["officename"]),
        "district": clamp(normalize_text(data.get("district")), FIELD_LIMITS["district"]),
        "statename": clamp(normalize_text(data.get("statename") or data.get("state")), FIELD_LIMITS["statename"])
    }
