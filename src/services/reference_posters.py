"""
Posters the team likes, as style references for the Template Studio's agents
(the user, 2026-10-27).

Each upload is read once, in the background, by the free vision model
(gemini_client.inspect_image): the layout of ours it is closest to, how its
headline is written, how much text it carries, and what is worth copying.
Its main colours are measured from the image itself, with no model.

The agents get the reading as notes in their prompts (notes(), under the
admin's "Reference posters" context switch), and the first draft of a round
takes the layout the references prefer (preferred_layout(), in variety.plan).
A poster is retired rather than deleted, so its reading stays on record.
"""
import io
import logging
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from src.models.studio import StudioReferencePoster

logger = logging.getLogger("gmap_scraper.reference_posters")

EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
MIME = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
MAX_BYTES = 15 * 1024 * 1024
# Smaller than this, the vision model cannot read the poster's words.
MIN_SIDE = 400
# How many posters' notes go into a prompt: the newest, so it stays short.
NOTES_LIMIT = 6

LAYOUT_WORDS = {
    "classic": "the photo across the top, the headline and benefits in a block below it",
    "list": "the benefits as a vertical list with round icons, the offer in a card",
    "banner": "the photo fills the whole poster, the text sits over it on one side",
    "mirror": "the photo on one half, the text on the other half",
    "spotlight": "one big photo, with only a small badge of text",
}

QUESTION = (
    "This is a WhatsApp marketing poster the team likes. It invites shop owners in India to become SBI "
    "bank kiosk (Customer Service Point) operators with Eko. Describe its design so a designer can follow "
    "it in new posters. Answer in English, as JSON with these keys:\n"
    '"layout": the closest of ' + "; ".join(f'"{k}" ({v})' for k, v in LAYOUT_WORDS.items()) + ";\n"
    '"headline_style": how the headline is written (length, tone, a question or a promise, numbers);\n'
    '"text_amount": "little", "some" or "a lot";\n'
    '"colours": the main colours in words;\n'
    '"what_to_copy": up to three short things that make it work, each one sentence.'
)


class PosterRefused(ValueError):
    """The upload cannot be used; the message says why."""


def check_image(data: bytes) -> str:
    """The file extension for an uploaded poster, or PosterRefused if it is not one."""
    from PIL import Image

    if len(data) > MAX_BYTES:
        raise PosterRefused(f"The poster is {len(data) / 1024 / 1024:.1f} MB; at most {MAX_BYTES // 1024 // 1024} MB.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            kind, (w, h) = im.format, im.size
    except Exception:
        raise PosterRefused("That file is not an image (JPG, PNG or WebP).")
    if kind not in EXTENSIONS:
        raise PosterRefused("Only JPG, PNG or WebP posters can be used.")
    if min(w, h) < MIN_SIDE:
        raise PosterRefused(f"The poster is {w}×{h}; at least {MIN_SIDE} pixels a side is needed to read its words.")
    return EXTENSIONS[kind]


def palette(data: bytes, n: int = 5) -> List[str]:
    """The poster's main colours, most used first, as #rrggbb."""
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        small = im.convert("RGB").resize((120, 120))
    quant = small.quantize(colors=n * 2, method=Image.Quantize.MEDIANCUT)
    pal = quant.getpalette() or []
    counts = sorted(quant.getcolors() or [], reverse=True)
    out = []
    for _count, index in counts:
        r, g, b = pal[index * 3:index * 3 + 3]
        hexed = f"#{r:02x}{g:02x}{b:02x}"
        if hexed not in out:
            out.append(hexed)
        if len(out) == n:
            break
    return out


def add(db: Session, media_id: str, data: bytes, *, note: Optional[str], uploaded_by: Optional[str]) -> StudioReferencePoster:
    try:
        colours = palette(data)
    except Exception:
        colours = None
    row = StudioReferencePoster(poster_id=uuid.uuid4().hex, media_id=media_id, note=(note or "").strip()[:300] or None,
                                uploaded_by=uploaded_by, active=True, palette=colours)
    db.add(row)
    db.commit()
    return row


def _clean(style: dict) -> dict:
    from src.services.poster_renderer import LAYOUTS

    layout = str(style.get("layout") or "").strip().lower()
    copy = style.get("what_to_copy") or []
    if isinstance(copy, str):
        copy = [copy]
    return {
        "layout": layout if layout in LAYOUTS else None,
        "headline_style": str(style.get("headline_style") or "")[:200] or None,
        "text_amount": str(style.get("text_amount") or "")[:20] or None,
        "colours": str(style.get("colours") or "")[:150] or None,
        "what_to_copy": [str(x)[:200] for x in copy if str(x).strip()][:3],
    }


def read(poster_id: str) -> None:
    """Background: the vision model reads the poster once. A failure is recorded, and Read again retries."""
    from src.database import SessionLocal
    from src.services import template_studio
    from src.services.gemini_client import GeminiClient

    db = SessionLocal()
    try:
        row = db.get(StudioReferencePoster, poster_id)
        if row is None:
            return
        try:
            data = template_studio._read_media(row.media_id)
            ext = "." + row.media_id.rsplit(".", 1)[-1]
            row.style = _clean(GeminiClient().inspect_image(data, MIME.get(ext, "image/jpeg"), QUESTION))
            row.read_error = None
        except Exception as e:
            logger.warning(f"reference_posters event=READ_FAILED poster={poster_id} reason={str(e)[:160]}")
            row.read_error = f"The free vision model could not read it: {str(e)[:200]}"
        row.read_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def listing(db: Session) -> List[StudioReferencePoster]:
    return (db.query(StudioReferencePoster)
            .order_by(StudioReferencePoster.active.desc(), StudioReferencePoster.created_at.desc()).all())


def set_active(db: Session, poster_id: str, active: bool) -> Optional[StudioReferencePoster]:
    row = db.get(StudioReferencePoster, poster_id)
    if row:
        row.active = active
        db.commit()
    return row


def _in_use(db: Session) -> List[StudioReferencePoster]:
    return (db.query(StudioReferencePoster)
            .filter(StudioReferencePoster.active.is_(True), StudioReferencePoster.style.isnot(None))
            .order_by(StudioReferencePoster.created_at.desc()).all())


def notes(db: Session) -> List[str]:
    """One line per reference poster in use, newest first, for the agents' prompts."""
    out = []
    for r in _in_use(db)[:NOTES_LIMIT]:
        s = r.style or {}
        parts = []
        if s.get("layout"):
            parts.append(f"layout: {LAYOUT_WORDS[s['layout']]}")
        if s.get("headline_style"):
            parts.append(f"headline: {s['headline_style']}")
        if s.get("text_amount"):
            parts.append(f"text: {s['text_amount']}")
        if s.get("what_to_copy"):
            parts.append("what works: " + " ".join(s["what_to_copy"]))
        if parts:
            out.append((f"“{r.note}” — " if r.note else "") + "; ".join(parts))
    return out


def preferred_layout(db: Session) -> Optional[str]:
    """The layout most of the team's reference posters are closest to, if any."""
    counts = Counter((r.style or {}).get("layout") for r in _in_use(db))
    counts.pop(None, None)
    return counts.most_common(1)[0][0] if counts else None
