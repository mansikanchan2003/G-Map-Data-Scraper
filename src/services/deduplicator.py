import re
import hashlib
from typing import Optional

def normalize_for_dedup(s: Optional[str]) -> str:
    """Normalize string for dedup comparison: lowercase, alphanumeric only."""
    if not s:
        return ""
    # Remove common business suffixes that cause false differences
    cleaned = s.lower()
    cleaned = re.sub(r'\b(pvt|ltd|private|limited|inc|corp|co|llp|branch|outlet)\b', '', cleaned)
    return re.sub(r'[^a-z0-9]', '', cleaned)

def extract_place_id(maps_url: Optional[str]) -> Optional[str]:
    """
    Extract place identifier or CID from Google Maps URL if available.
    """
    if not maps_url:
        return None
        
    # Match ChIJ... (standard Google Place ID format)
    match_chij = re.search(r'(ChIJ[a-zA-Z0-9_-]{23,})', maps_url)
    if match_chij:
        return match_chij.group(1)
        
    # Match cid=...
    match_cid = re.search(r'cid=([0-9]+)', maps_url)
    if match_cid:
        return f"cid_{match_cid.group(1)}"
        
    # Match !1s0x... (hex place id)
    match_hex = re.search(r'!1s(0x[0-9a-fA-F]+:[0-9a-fA-F]+)', maps_url)
    if match_hex:
        return match_hex.group(1)

    return None

def generate_dedup_key(
    name: str,
    address: Optional[str] = None,
    phone: Optional[str] = None,
    place_id: Optional[str] = None,
    maps_url: Optional[str] = None
) -> str:
    """
    Generate composite deduplication key following strict hierarchy:
    1. Google Maps place identifier
    2. normalized phone + normalized address
    3. normalized business name + normalized address
    4. normalized business name + normalized phone
    5. fallback with URL hash or unique hash

    CRITICAL RULE: Never deduplicate on business name alone.
    """
    # 1. Place identifier (explicit or extracted from URL)
    pid = place_id or extract_place_id(maps_url)
    if pid and len(pid) >= 8:
        return f"pid:{pid}"

    norm_name = normalize_for_dedup(name)
    norm_phone = re.sub(r'\D', '', phone) if phone else ""
    if len(norm_phone) >= 10:
        norm_phone = norm_phone[-10:] # last 10 digits
        
    norm_addr = normalize_for_dedup(address)

    # 2. Normalized phone + Normalized address
    if norm_phone and norm_addr:
        return f"phone_addr:{norm_phone}:{norm_addr[:50]}"

    # 3. Normalized name + Normalized address
    if norm_name and norm_addr:
        return f"name_addr:{norm_name[:40]}:{norm_addr[:50]}"

    # 4. Normalized name + Normalized phone
    if norm_name and norm_phone:
        return f"name_phone:{norm_name[:40]}:{norm_phone}"

    # 5. Discriminator fallback: use maps_url hash if available to avoid colliding identical names
    if maps_url:
        url_hash = hashlib.sha256(maps_url.encode('utf-8')).hexdigest()[:12]
        return f"name_url:{norm_name[:30]}:{url_hash}"

    # 6. Safe unique fallback using full name hash
    fallback_hash = hashlib.sha256(f"{name}_{address}_{phone}".encode('utf-8')).hexdigest()[:12]
    return f"fallback:{norm_name[:30]}:{fallback_hash}"

def generate_business_id(name: str, phone: Optional[str], lat: Optional[float], lng: Optional[float], maps_url: Optional[str] = None) -> str:
    """Deterministic 16-char hex identifier for Business record."""
    norm_name = normalize_for_dedup(name)
    norm_phone = re.sub(r'\D', '', phone) if phone else ""
    loc_part = f"{lat:.4f}_{lng:.4f}" if lat is not None and lng is not None else (maps_url or "noloc")
    s = f"{norm_name}_{norm_phone}_{loc_part}".encode('utf-8')
    return hashlib.sha256(s).hexdigest()[:16]
