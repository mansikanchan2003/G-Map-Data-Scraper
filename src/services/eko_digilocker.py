"""
Documents from DigiLocker, through Eko's own API platform (eps.eko.in/docs).

On the upload page a person can fetch their Aadhaar, PAN and Driving Licence
from DigiLocker in one go, and then upload only what DigiLocker did not give
(the team's call, 30 Oct 2026):

1. "Create DigiLocker URL" gives a one-time DigiLocker link for them, asking
   for all three, with our page as where DigiLocker sends them back.
2. They sign in on DigiLocker's own site and approve sharing. We never see
   their password or OTP.
3. Back on our page, "Get DigiLocker Document" is called once per type and
   returns that document's verified details (not a scan of the card). A type
   they do not have, or did not share, comes back refused, and costs nothing.

Each document's details are turned into a one-page PDF and filed as its own
record, which counts for that row of the upload page, so the inbox, Drive and
the team see it like an upload. The Aadhaar number is kept as its last four
digits only, whatever comes.

Production's replies are not the documented shape: Aadhaar's details sit in
data itself (seen 30 Oct 2026). PAN's and the licence's had not been seen
when this was written, so they are read leniently and their first replies'
shape is logged (keys and numbers only, never text) to check against.

Eko charges for each successful fetch (Rs 2.50 + GST per document), so a
document is fetched once: reloading the return page does not fetch it again.
The Status API is billable too and is not used.

Credentials come from the environment: EKO_DEVELOPER_KEY, EKO_ACCESS_KEY,
EKO_INITIATOR_ID (the registered mobile number) and EKO_BASE_URL. Without
them the page simply does not offer DigiLocker.
"""
import base64
import hashlib
import hmac
import io
import logging
import os
import re
import secrets
import time
from typing import Optional

import requests

logger = logging.getLogger("gmap_scraper.digilocker")

PRODUCTION_BASE_URL = "https://api.eko.in/ekoicici/v3"
CREATE_PATH = "/tools/kyc/digilocker"
DOCUMENT_PATH = "/tools/kyc/digilocker/document"
DOCUMENT_TYPE = "AADHAAR"
# Every type Eko's DigiLocker API serves ("document_type should be AADHAAR/PAN/DRIVING_LICENSE").
DOCUMENT_TYPES = ("AADHAAR", "PAN", "DRIVING_LICENSE")
TITLES = {"AADHAAR": "Aadhaar", "PAN": "PAN Card", "DRIVING_LICENSE": "Driving Licence"}
# The types the upload page asks for. PAN is left out: on 30 Oct 2026 production
# answered a PAN fetch "success" with gender and date of birth only, no name or
# number, so nothing could be filed and the fetch was likely billed. Set
# EKO_DIGILOCKER_DOCUMENTS to add it back once Eko returns the details.
DEFAULT_TYPES = ("AADHAAR", "DRIVING_LICENSE")


def enabled_types() -> tuple:
    raw = os.environ.get("EKO_DIGILOCKER_DOCUMENTS")
    if not raw:
        return DEFAULT_TYPES
    picked = tuple(t for t in DOCUMENT_TYPES if t in {x.strip().upper() for x in raw.split(",")})
    return picked or DEFAULT_TYPES
TIMEOUT = 25

# A DigiLocker session left this long is started afresh on the next tap.
SESSION_MINUTES = 30


class DigiLockerError(Exception):
    """Something the person can be told: the link could not be made or the details not fetched."""


def configured() -> bool:
    return all(os.environ.get(k) for k in ("EKO_DEVELOPER_KEY", "EKO_ACCESS_KEY", "EKO_INITIATOR_ID"))


def base_url() -> str:
    return (os.environ.get("EKO_BASE_URL") or PRODUCTION_BASE_URL).rstrip("/")


def signature(access_key: str, timestamp: str) -> str:
    """
    Eko's per-request secret-key: base64(HMAC-SHA256(timestamp, base64(access_key))).
    The HMAC key is the base64 string itself, not decoded back to bytes.
    """
    key = base64.b64encode(access_key.encode()).decode()
    digest = hmac.new(key.encode(), timestamp.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _headers() -> dict:
    timestamp = str(int(time.time() * 1000))
    return {
        "developer_key": os.environ["EKO_DEVELOPER_KEY"],
        "secret-key": signature(os.environ["EKO_ACCESS_KEY"], timestamp),
        "secret-key-timestamp": timestamp,
        "content-type": "application/json",
    }


def client_ref_id() -> str:
    """Unique per call, 10-20 letters and digits."""
    return "AGM" + secrets.token_hex(7)


def _post(path: str, body: dict) -> dict:
    body = {"initiator_id": os.environ["EKO_INITIATOR_ID"], "client_ref_id": client_ref_id(), **body}
    try:
        r = requests.post(base_url() + path, json=body, headers=_headers(), timeout=TIMEOUT)
    except requests.RequestException as e:
        logger.warning(f"digilocker event=REQUEST_FAILED path={path} error={type(e).__name__}")
        raise DigiLockerError("DigiLocker could not be reached just now. Please try again in a minute.")
    try:
        out = r.json()
    except ValueError:
        out = {}
    if r.status_code != 200 or not isinstance(out, dict):
        logger.warning(f"digilocker event=HTTP_{r.status_code} path={path} message={str(out.get('message') if isinstance(out, dict) else '')[:200]}")
        raise DigiLockerError("DigiLocker is not available just now. Please upload a photo of your Aadhaar instead.")
    return out


def create_url(redirect_url: str, types=DOCUMENT_TYPES) -> dict:
    """A one-time DigiLocker link asking for these documents: {"reference_id", "url"}."""
    out = _post(CREATE_PATH, {"document_requested": list(types), "redirect_url": redirect_url})
    data = out.get("data") or {}
    if out.get("status") != 0 or not data.get("url") or data.get("reference_id") in (None, ""):
        logger.warning(f"digilocker event=CREATE_REFUSED status={out.get('status')} "
                       f"type={out.get('response_type_id')} message={str(out.get('message'))[:200]}")
        raise DigiLockerError("DigiLocker could not be opened just now. Please try again, or upload a photo instead.")
    result = {"reference_id": str(data["reference_id"]), "url": data["url"]}
    # Not documented as returned, but "Get Document" asks for one; kept if it comes.
    if data.get("verification_id"):
        result["verification_id"] = str(data["verification_id"])
    return result


def _mask(number) -> Optional[str]:
    """An Aadhaar number as XXXX-XXXX-1234: a full number must never be kept."""
    digits = re.sub(r"\D", "", str(number or ""))
    return f"XXXX-XXXX-{digits[-4:]}" if len(digits) >= 4 else None


def _address(addr) -> dict:
    addr = addr if isinstance(addr, dict) else {}
    return {
        "house": addr.get("house"),
        "street": ", ".join(str(addr[k]) for k in ("street", "landmark", "po") if addr.get(k)),
        "village_or_city": addr.get("vtc") or addr.get("village_or_city") or addr.get("city"),
        "district": addr.get("dist") or addr.get("district") or addr.get("subdist"),
        "state": addr.get("state"),
        "pincode": addr.get("pincode"),
    }


# Where a PAN's or licence's number may be, in a reply not yet seen.
NUMBER_KEYS = ("pan", "pan_number", "pan_no", "dl_number", "dl_no", "licence_number", "license_number",
               "document_number", "id_number", "number", "uid")
# Not listed among a document's other details: the call's ids, links, images and the address.
_NOT_FIELDS = {"tid", "reference_id", "verification_id", "status", "photo", "photo_link", "image", "split_address",
               "address", "documents", "verification_status", "document_type", "name", "dob", "gender", "care_of"}


def _from_production(data, doc_type: str = DOCUMENT_TYPE) -> Optional[dict]:
    """
    Production's reply mapped onto the documented document, so the rest reads
    one shape. Aadhaar's (30 Oct 2026) has the details in data itself: name,
    dob, gender, uid (the number), care_of, split_address and photo_link.
    """
    if not isinstance(data, dict):
        return None
    number_key = next((k for k in NUMBER_KEYS if data.get(k)), None)
    if not data.get("name") and not number_key:
        return None
    if doc_type == DOCUMENT_TYPE and not (data.get("uid") or data.get("split_address") or data.get("masked_aadhaar")):
        return None
    photo = data.get("photo_link") or data.get("photo") or data.get("image")
    doc = {
        "document_type": doc_type,
        "name": data.get("name"),
        "dob": data.get("dob"),
        "gender": data.get("gender"),
        "care_of": data.get("care_of"),
        # A link would need fetching; only an inline image is drawn.
        "photo": photo if isinstance(photo, str) and photo and not photo.startswith("http") else None,
        "address": _address(data.get("split_address") or data.get("address")),
        "fields": {},
    }
    if doc_type == DOCUMENT_TYPE:
        # uid is 12 characters; whether masked or not, only the last four are kept.
        doc["masked_aadhaar"] = _mask(data.get("uid") or data.get("masked_aadhaar"))
    else:
        doc["number"] = str(data[number_key]) if number_key else None
        doc["fields"] = {k: v for k, v in data.items()
                         if k not in _NOT_FIELDS and k != number_key
                         and isinstance(v, (str, int, float)) and str(v).strip()}
    return doc


def _find(node, doc_type: str, depth: int = 0) -> Optional[dict]:
    """The document where the documentation puts it (data.documents), or wherever else it is."""
    if depth > 4:
        return None
    if isinstance(node, dict):
        if str(node.get("document_type") or "").upper() == doc_type and ("name" in node or "masked_aadhaar" in node):
            return node
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        found = _find(child, doc_type, depth + 1)
        if found:
            return found
    return None


def _shape(node, depth: int = 0):
    """A reply's keys and numbers, never its text: it may hold a person's details."""
    if isinstance(node, dict) and depth < 3:
        return {k: _shape(v, depth + 1) for k, v in list(node.items())[:15]}
    if isinstance(node, list):
        return f"list[{len(node)}]"
    if isinstance(node, (int, float, bool)) or node is None:
        return node
    # Every piece of text is hidden: a short one can still be a date of birth or a PIN code.
    return f"str[{len(str(node))}]"


# DigiLocker can hand back before Eko has the document: a fetch can come back
# accepted with ids only. A failed fetch is free, so that one is asked again.
FETCH_TRIES = 4
FETCH_WAIT_SECONDS = 3


def fetch(doc_type: str, reference_id: str, verification_id: Optional[str] = None) -> Optional[dict]:
    """
    One document's verified details, or None when DigiLocker has none to give
    (not finished, not shared, or not in their DigiLocker). Raises
    DigiLockerError when it cannot be fetched at all.
    """
    for attempt in range(1, FETCH_TRIES + 1):
        out = _post(DOCUMENT_PATH, {
            # One type as a string here; a list is refused ("document_type should be
            # AADHAAR/PAN/DRIVING_LICENSE"), though creating the link takes a list.
            "document_type": doc_type,
            "reference_id": str(reference_id),
            "verification_id": str(verification_id or reference_id),
        })
        if out.get("status") != 0:
            logger.info(f"digilocker event=NOT_READY doc={doc_type} type={out.get('response_type_id')} "
                        f"message={str(out.get('message'))[:200]}")
            return None
        data = out.get("data")
        documented = _find(out, doc_type)
        doc = documented or _from_production(data, doc_type)
        if doc:
            if doc_type != DOCUMENT_TYPE and not documented:
                # Not seen when this was written: its shape, to check the reading against.
                logger.info(f"digilocker event=FETCHED doc={doc_type} shape={_shape(out)}")
            return doc
        logger.warning(f"digilocker event=EMPTY doc={doc_type} try={attempt} shape={_shape(out)}")
        if not (isinstance(data, dict) and set(data) <= {"status", "tid"}):
            return None
        if attempt < FETCH_TRIES:
            time.sleep(FETCH_WAIT_SECONDS)
    return None


def fetch_aadhaar(reference_id: str, verification_id: Optional[str] = None) -> Optional[dict]:
    return fetch(DOCUMENT_TYPE, reference_id, verification_id)


def summary(doc: dict) -> dict:
    """What is kept on the conversation: the details, an Aadhaar number masked, and no photo."""
    addr = doc.get("address") or {}
    out = {
        "name": doc.get("name"),
        "dob": doc.get("dob"),
        "gender": doc.get("gender"),
        "address": ", ".join(str(addr[k]) for k in ("house", "street", "village_or_city", "district", "state")
                             if addr.get(k)),
        "pincode": addr.get("pincode"),
    }
    if str(doc.get("document_type") or DOCUMENT_TYPE).upper() == DOCUMENT_TYPE:
        out["masked_aadhaar"] = _mask(doc.get("masked_aadhaar"))
    else:
        out["number"] = doc.get("number")
    return out


_GENDER = {"M": "Male", "F": "Female", "T": "Transgender"}


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    names = ("DejaVuSans-Bold.ttf", "arialbd.ttf") if bold else ("DejaVuSans.ttf", "arial.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _wrap(draw, text: str, font, width: int) -> list:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def _pretty(key: str) -> str:
    return str(key).replace("_", " ").strip().capitalize()


def pdf(doc: dict, verified_at: str) -> bytes:
    """A one-page A4 PDF of a document's verified details, filed as that document."""
    from PIL import Image, ImageDraw

    page = Image.new("RGB", (1240, 1754), "white")  # A4 at 150 dpi
    draw = ImageDraw.Draw(page)
    navy, muted, ok = (12, 37, 49), (85, 112, 128), (15, 138, 95)

    draw.rectangle((0, 0, 1240, 190), fill=navy)
    kind = str(doc.get("document_type") or DOCUMENT_TYPE).upper()
    aadhaar = kind == DOCUMENT_TYPE
    draw.text((80, 48), f"{TITLES.get(kind, kind.title())} - from DigiLocker", font=_font(48, True), fill="white")
    draw.text((80, 120), "Fetched from DigiLocker with the applicant's consent, through Eko's API.",
              font=_font(26), fill=(213, 227, 231))

    top = 250
    photo = doc.get("photo")
    if photo:
        try:
            img = Image.open(io.BytesIO(base64.b64decode(photo))).convert("RGB")
            img.thumbnail((300, 380))
            page.paste(img, (860, top))
            draw.rectangle((858, top - 2, 862 + img.width, top + 2 + img.height), outline=(213, 227, 231), width=2)
        except Exception:
            logger.info("digilocker event=PHOTO_UNREADABLE")

    s = summary(doc)
    rows = [
        ("Name", s["name"]),
        ("Aadhaar number" if aadhaar else {"PAN": "PAN", "DRIVING_LICENSE": "Licence number"}.get(kind, "Number"),
         s.get("masked_aadhaar") if aadhaar else s.get("number")),
        ("Date of birth", s["dob"]),
        ("Gender", _GENDER.get(str(s["gender"] or "").upper(), s["gender"])),
        ("Care of", doc.get("care_of")),
        ("Address", s["address"]),
        ("PIN code", s["pincode"]),
        ("Issued on", doc.get("issue_date")),
    ]
    # A PAN's or licence's other details, as they come (validity, father's name, ...).
    rows += [(_pretty(k), v) for k, v in list((doc.get("fields") or {}).items())[:8]]
    label, value = _font(26), _font(34, True)
    y = top
    for name, text in rows:
        if not text:
            continue
        draw.text((80, y), name.upper(), font=label, fill=muted)
        y += 38
        for line in _wrap(draw, str(text), value, 740 if y < top + 400 else 1080):
            draw.text((80, y), line, font=value, fill=navy)
            y += 46
        y += 26

    y = max(y, top + 420) + 20
    draw.rounded_rectangle((80, y, 1160, y + 110), radius=18, fill=(230, 246, 239))
    draw.text((110, y + 22), "Verified by DigiLocker", font=_font(32, True), fill=ok)
    note = " The first eight digits of the number are masked." if aadhaar else ""
    draw.text((110, y + 66), f"Fetched on {verified_at}.{note}", font=_font(24), fill=muted)

    buf = io.BytesIO()
    page.save(buf, "PDF", resolution=150.0)
    return buf.getvalue()
