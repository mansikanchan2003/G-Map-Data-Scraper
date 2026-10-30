"""
Aadhaar from DigiLocker, through Eko's own API platform (eps.eko.in/docs).

On the upload page a person can verify their Aadhaar with DigiLocker in
place of uploading a photo of it:

1. "Create DigiLocker URL" gives a one-time DigiLocker link for them, with
   our page as where DigiLocker sends them back.
2. They sign in on DigiLocker's own site and approve sharing their Aadhaar.
   We never see their password or OTP.
3. Back on our page, "Get DigiLocker Document" returns the verified details:
   name, date of birth, gender, the Aadhaar number with the first eight
   digits masked, the address and the photo. Never the full number.

Those details are turned into a one-page PDF and filed as the Aadhaar
document, like an upload, so the inbox, Drive and the team see it the same
way. Only the masked number and the details are kept on the conversation.

Eko charges for each successful fetch (Rs 2.50 + GST), so a fetch is made
once per DigiLocker session: reloading the return page does not fetch again.
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


def create_url(redirect_url: str) -> dict:
    """A one-time DigiLocker link: {"reference_id", "url"}."""
    out = _post(CREATE_PATH, {"document_requested": [DOCUMENT_TYPE], "redirect_url": redirect_url})
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


def _find_aadhaar(node, depth: int = 0) -> Optional[dict]:
    """The Aadhaar document wherever the reply puts it (the documented data.documents, or elsewhere)."""
    if depth > 4:
        return None
    if isinstance(node, dict):
        if str(node.get("document_type") or "").upper() == DOCUMENT_TYPE and ("name" in node or "masked_aadhaar" in node):
            return node
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        found = _find_aadhaar(child, depth + 1)
        if found:
            return found
    return None


def _shape(node, depth: int = 0):
    """A reply's keys and short codes, never its text: it may hold a person's details."""
    if isinstance(node, dict) and depth < 3:
        return {k: _shape(v, depth + 1) for k, v in list(node.items())[:15]}
    if isinstance(node, list):
        return f"list[{len(node)}]"
    if isinstance(node, (int, float, bool)) or node is None:
        return node
    text = str(node)
    # Codes and statuses are short and upper-case or numeric; anything else is hidden.
    return text if len(text) <= 12 and re.fullmatch(r"[A-Z0-9_\-]*", text) else f"str[{len(text)}]"


# DigiLocker hands back before Eko has the document: the first fetch can come
# back accepted but empty. A failed fetch is free, so it is asked again.
FETCH_TRIES = 4
FETCH_WAIT_SECONDS = 3


def fetch_aadhaar(reference_id: str, verification_id: Optional[str] = None) -> Optional[dict]:
    """
    The verified Aadhaar details, or None while the person has not finished
    on DigiLocker. Raises DigiLockerError when it cannot be fetched at all.
    """
    for attempt in range(1, FETCH_TRIES + 1):
        out = _post(DOCUMENT_PATH, {
            # One type as a string here; a list is refused ("document_type should be
            # AADHAAR/PAN/DRIVING_LICENSE"), though creating the link takes a list.
            "document_type": DOCUMENT_TYPE,
            "reference_id": str(reference_id),
            "verification_id": str(verification_id or reference_id),
        })
        if out.get("status") != 0:
            logger.info(f"digilocker event=NOT_READY type={out.get('response_type_id')} message={str(out.get('message'))[:200]}")
            return None
        doc = _find_aadhaar(out)
        if doc:
            return doc
        logger.warning(f"digilocker event=NO_AADHAAR try={attempt} shape={_shape(out)}")
        if attempt < FETCH_TRIES:
            time.sleep(FETCH_WAIT_SECONDS)
    return None


def summary(doc: dict) -> dict:
    """What is kept on the conversation: the details, with the number masked and no photo."""
    addr = doc.get("address") or {}
    return {
        "name": doc.get("name"),
        "dob": doc.get("dob"),
        "gender": doc.get("gender"),
        "masked_aadhaar": doc.get("masked_aadhaar"),
        "address": ", ".join(str(addr[k]) for k in ("house", "street", "village_or_city", "district", "state")
                             if addr.get(k)),
        "pincode": addr.get("pincode"),
    }


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


def pdf(doc: dict, verified_at: str) -> bytes:
    """A one-page A4 PDF of the verified details, filed as the Aadhaar document."""
    from PIL import Image, ImageDraw

    page = Image.new("RGB", (1240, 1754), "white")  # A4 at 150 dpi
    draw = ImageDraw.Draw(page)
    navy, muted, ok = (12, 37, 49), (85, 112, 128), (15, 138, 95)

    draw.rectangle((0, 0, 1240, 190), fill=navy)
    draw.text((80, 48), "Aadhaar - verified via DigiLocker", font=_font(48, True), fill="white")
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
        ("Aadhaar number", s["masked_aadhaar"]),
        ("Date of birth", s["dob"]),
        ("Gender", _GENDER.get(str(s["gender"] or "").upper(), s["gender"])),
        ("Address", s["address"]),
        ("PIN code", s["pincode"]),
        ("Issued on", doc.get("issue_date")),
    ]
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
    draw.text((110, y + 66), f"Fetched on {verified_at}. The first eight digits of the number are masked.",
              font=_font(24), fill=muted)

    buf = io.BytesIO()
    page.save(buf, "PDF", resolution=150.0)
    return buf.getvalue()
