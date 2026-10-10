"""
Keeps track of which image prompts work, and makes the next one from them.

Every image the Studio asks for is recorded (models/studio.py): the prompt,
the style of wording around the scene, how the check judged it, and what the
reviewer did with it. Three things are then learned from that record:

1. **Which wording to use.** A scene is wrapped in one of several STYLES. The
   style with the best record is used; one that keeps failing stops being
   chosen, and an untried one is tried before a failing one is used again.
2. **What to ask for.** The writing model is shown the scenes that made good
   photos and the ones that came out wrong, and why, and asked to write a
   scene that beats the best so far.
3. **Whether a sign is worth trying.** Free image models often draw Indic
   lettering as gibberish. While signs keep failing, the attempt is skipped,
   saving the few free images a day, and tried again now and then in case
   something has changed.

"Worked" means the check passed and the reviewer did not replace it; a photo
the reviewer kept, by approving its draft, is the strongest evidence of all.
"""
import logging
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.studio import StudioImagePrompt
from src.services import creative_brief

logger = logging.getLogger("gmap_scraper.image_prompts")

UNUSED, IN_REVIEW, KEPT, REPLACED, DRAFT_REJECTED = "unused", "in_review", "kept", "replaced", "draft_rejected"

# What every photo shows, whatever the scene: the team's own reference photos
# of real Customer Service Points (2026-10-10). Fixed here rather than left to
# the scene, after a photo made the operator look like a sage.
CSP_SETTING = (
    "The kiosk operator looks like a professional: neatly groomed, in professional attire — a man "
    "in a collared shirt or a plain T-shirt, a woman in a saree, kurti or salwar suit — seated "
    "behind the counter with a laptop or desktop computer, a fingerprint scanner and a small "
    "printer. Not a sage, monk, priest or holy man: no saffron robe or turban, no tilak, no long "
    "ascetic beard. The customers are ordinary local people in everyday clothes, standing at a "
    "wooden or laminated counter. The wall behind the operator is covered, as in a real SBI "
    "Customer Service Point, with large SBI-blue banners bearing the round SBI logo, colourful "
    "posters for account opening, money transfer and Aadhaar cash withdrawal, printed notices of "
    "rules, and framed training certificates."
)
# Free image models draw lettering as gibberish, so the wall's posters are
# asked for out of focus: they read as posters without legible text.
_NO_TEXT = ("The posters and banners on the wall are softly out of focus in the background, so none "
            "of their lettering is legible. No sharp text, numbers or watermarks anywhere in the "
            "foreground. Not an illustration, not a 3D render, not glossy stock photography.")


def _place(state: Optional[str]) -> str:
    return f"{state}, India" if state else "India"


# The wording around the agent's scene. "short" is the brief prompt that made
# the photo the team liked on 2026-10-09, so it is tried first while neither
# has a record; "documentary" is the Studio's original, longer one, with
# framing that leaves room for the poster's text.
STYLES = {
    "short": lambda scene, state: (
        f"Candid documentary photo inside a small State Bank of India customer service point in "
        f"{_place(state)}. {scene} Natural daylight, 35mm, real skin texture."
    ),
    "documentary": lambda scene, state: (
        f"A candid, unposed documentary photograph taken inside a small State Bank of India "
        f"customer service point (a bank kiosk run by a local shopkeeper) in {_place(state)}. "
        f"{scene} The kiosk operator sits behind a counter with a laptop, a fingerprint scanner "
        f"and a small receipt printer, serving a customer at the counter. "
        f"Shot on a 35mm lens at eye level in natural daylight, slight film grain, true-to-life "
        f"colours, real skin texture with pores and imperfections, a lived-in room with papers "
        f"and cables. The people are in the centre of the frame and the lower quarter is the "
        f"front of the counter."
    ),
}
DEFAULT_STYLE = "short"


def build(style: str, scene: str, state: Optional[str], phrase: Optional[str] = None,
          language_code: Optional[str] = None, direction: str = "") -> str:
    """
    The full prompt: the style's wording around the scene, the shot and
    operator the variant was given (variety.photo_direction), the kiosk as it
    must look, then the text rule.
    """
    base = " ".join(x for x in (STYLES.get(style, STYLES[DEFAULT_STYLE])(scene, state), direction, CSP_SETTING) if x)
    if not phrase:
        return f"{base} {_NO_TEXT}"
    lang = creative_brief.LANGUAGES[language_code]
    return (
        f"{base} Above the counter, in sharp focus, hangs one clean, printed sign with large, "
        f"dark, clearly legible lettering that reads exactly: \"{phrase}\" — in {lang['name']} "
        f"({lang['script']} script), spelled exactly as given, nothing added. Every other poster "
        f"on the wall is softly out of focus, its lettering not legible. Not an illustration, not "
        f"a 3D render, not glossy stock photography."
    )


def new_seed() -> int:
    """A seed chosen here rather than by the Space, so a good image can be made again."""
    return random.randint(0, 2**31 - 1)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def _session():
    from src.database import SessionLocal
    return SessionLocal()


def record(*, template_id: Optional[str], kind: str, style: str, prompt: str, scene: Optional[str],
           phrase: Optional[str], language_code: Optional[str], state: Optional[str], model: Optional[str],
           seed: Optional[int], media_id: Optional[str], check: dict, checked: bool, passed: bool,
           gibberish: bool, outcome: str, note: Optional[str]) -> None:
    """
    Writes one image's record in a session of its own, so it is kept even if
    the draft that asked for it then fails. A failure to record never stops
    the draft.
    """
    db = _session()
    try:
        db.add(StudioImagePrompt(
            # Stamped here, not by the database: "which came first" decides the
            # sign re-test, and a database clock may only count whole seconds.
            prompt_id=uuid.uuid4().hex, created_at=datetime.now(timezone.utc),
            template_id=template_id, kind=kind, style=style,
            language_code=language_code, target_state=state, scene=scene, phrase=phrase, prompt=prompt,
            model=model, seed=seed, media_id=media_id, check=check, checked=checked, passed=passed,
            gibberish=gibberish, outcome=outcome, note=(note or "")[:300] or None,
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("image_prompts event=RECORD_FAILED")
    finally:
        db.close()


def with_db(fn, *args):
    """Runs fn(db, *args) in a session of its own, for callers that have none."""
    db = _session()
    try:
        return fn(db, *args)
    finally:
        db.close()


def in_review_ids(db: Session, template_id: str) -> List[str]:
    """The records of the photo a draft is showing now."""
    return [r.prompt_id for r in db.query(StudioImagePrompt.prompt_id)
            .filter(StudioImagePrompt.template_id == template_id, StudioImagePrompt.outcome == IN_REVIEW)]


def mark_ids(db: Session, prompt_ids: List[str], outcome: str) -> None:
    if prompt_ids:
        (db.query(StudioImagePrompt).filter(StudioImagePrompt.prompt_id.in_(prompt_ids))
         .update({StudioImagePrompt.outcome: outcome}, synchronize_session=False))
        db.commit()


def mark(db: Session, template_id: str, outcome: str) -> None:
    """What the reviewer did with a draft's current photo: kept it, or rejected the draft."""
    mark_ids(db, in_review_ids(db, template_id), outcome)


def sign_note(check: dict, phrase: str, passed: bool, checked: bool) -> Optional[str]:
    if not checked:
        return "the sign could not be checked"
    if passed:
        return None
    parts = []
    read = (check.get("sign_text") or "").strip()
    if read != phrase:
        parts.append(f'sign came out as "{read}" instead of "{phrase}"' if read else "no readable sign")
    if (check.get("other_text") or "").strip():
        parts.append(f'stray lettering "{check["other_text"].strip()[:60]}"')
    return "; ".join(parts + _look_problems(check)) or "failed the check"


def plain_note(check: dict, passed: bool, checked: bool) -> Optional[str]:
    if not checked:
        return "the photo could not be checked"
    if passed:
        return None
    parts = ["sharp lettering appeared where none was asked for"] if check.get("has_text") else []
    if check.get("operator_serving_customer") is False:
        parts.append("nobody serving a customer")
    return "; ".join(parts + _look_problems(check)) or "failed the check"


def _look_problems(check: dict) -> List[str]:
    parts = []
    if check.get("operator_professional") is False:
        parts.append("the operator did not look like a professional")
    if check.get("photorealistic") is False:
        parts.append("looked artificial")
    if check.get("anatomy_problems"):
        parts.append("distorted hands or faces")
    return parts


# ---------------------------------------------------------------------------
# Learning
# ---------------------------------------------------------------------------

def _worked(r: StudioImagePrompt) -> bool:
    return r.passed and r.outcome != REPLACED


def _judged(db: Session, kind: Optional[str] = None):
    q = db.query(StudioImagePrompt).filter(StudioImagePrompt.checked.is_(True))
    if kind:
        q = q.filter(StudioImagePrompt.kind == kind)
    return q


def style_record(db: Session, kind: str) -> Dict[str, dict]:
    """Tries and successes per style, for photos of one kind."""
    out = {s: {"tries": 0, "worked": 0, "gibberish": 0} for s in STYLES}
    for r in _judged(db, kind).all():
        rec = out.setdefault(r.style, {"tries": 0, "worked": 0, "gibberish": 0})
        rec["tries"] += 1
        rec["worked"] += int(_worked(r))
        rec["gibberish"] += int(r.gibberish)
    for rec in out.values():
        # Laplace-smoothed: an untried style scores 0.5, so it is tried
        # before one that has failed, and one success is not a certainty.
        rec["score"] = (rec["worked"] + 1) / (rec["tries"] + 2)
    return out


def choose_style(db: Session, kind: str) -> str:
    """The style with the best record; on a tie, the less tried, then the default."""
    rec = style_record(db, kind)
    order = list(STYLES)
    return max((s for s in rec if s in STYLES),
               key=lambda s: (rec[s]["score"], -rec[s]["tries"], -order.index(s)))


# Signs are skipped while their smoothed success, over every style, stays
# below this — none right in five or more tries — except every
# RETEST_EVERY-th photo. Over all styles, not the best one: per style, it
# would take five wasted images in each before any were saved.
SIGN_FLOOR = 0.15
RETEST_EVERY = 5


def sign_worth_trying(db: Session) -> bool:
    """
    Whether to spend an image on a sign. While signs keep coming out as
    gibberish they are skipped, but tried again after every few plain photos
    in case the models have improved.
    """
    rec = style_record(db, "sign").values()
    tries, worked = sum(r["tries"] for r in rec), sum(r["worked"] for r in rec)
    if (worked + 1) / (tries + 2) >= SIGN_FLOOR:
        return True
    last_sign = (db.query(StudioImagePrompt).filter(StudioImagePrompt.kind == "sign")
                 .order_by(StudioImagePrompt.created_at.desc()).first())
    since = db.query(StudioImagePrompt).filter(StudioImagePrompt.kind == "plain")
    if last_sign:
        since = since.filter(StudioImagePrompt.created_at > last_sign.created_at)
    return since.count() >= RETEST_EVERY - 1


def lessons(db: Session, limit_worked: int = 4, limit_failed: int = 6) -> dict:
    """
    What the writing model is shown before it writes a photo scene and a sign
    phrase: the photos that worked, best first, and the ones that did not,
    newest first, each with the reason.
    """
    rows = _judged(db).order_by(StudioImagePrompt.created_at.desc()).limit(200).all()
    rank = {KEPT: 0, IN_REVIEW: 1, DRAFT_REJECTED: 2, UNUSED: 3}
    good = sorted((r for r in rows if _worked(r) and r.scene),
                  key=lambda r: rank.get(r.outcome, 4))
    worked, seen = [], set()
    for r in good:
        if r.scene in seen:
            continue
        seen.add(r.scene)
        how = f'sign "{r.phrase}" came out right' if r.kind == "sign" else "clean photo"
        if r.outcome == KEPT:
            how += ", kept by the reviewer"
        worked.append(f'"{r.scene}" ({how})')
        if len(worked) == limit_worked:
            break

    failed = []
    for r in rows:
        if _worked(r) or not r.scene:
            continue
        why = r.note or "failed the check"
        if r.outcome == REPLACED:
            why = "the reviewer asked for another photo" + (f"; {r.note}" if r.note else "")
        failed.append(f'"{r.scene}"{" with sign " + repr(r.phrase) if r.kind == "sign" else ""}: {why}')
        if len(failed) == limit_failed:
            break

    signs = [r for r in rows if r.kind == "sign"]
    return {
        "worked": worked,
        "failed": failed,
        "signs_tried": len(signs),
        "signs_right": sum(1 for r in signs if _worked(r)),
    }


def lesson_lines(photos: Optional[dict]) -> List[str]:
    """The lessons as prompt lines; empty before any photo has been judged."""
    if not photos or not (photos.get("worked") or photos.get("failed")):
        return []
    lines = [f"WORKED: {w}" for w in photos["worked"]] + [f"FAILED: {f}" for f in photos["failed"]]
    if photos.get("signs_tried"):
        lines.append(f"Signs so far: {photos['signs_right']} of {photos['signs_tried']} came out spelled right"
                     " — short, common words have the best chance.")
    return lines


PHOTOS_HEADING = (
    "PHOTOS SO FAR — every photo is checked, and the reviewer keeps it or asks for another. Write "
    "photo_scene to make a better photo than the best of these: build on what worked, avoid what failed:"
)


def summary(db: Session, recent: int = 30) -> dict:
    """The record as the Studio page shows it."""
    rows = db.query(StudioImagePrompt).order_by(StudioImagePrompt.created_at.desc()).limit(recent).all()
    return {
        "styles": [{"kind": kind, "style": style, **{k: v for k, v in rec.items() if k != "score"},
                    "score": round(rec["score"], 2), "chosen_next": style == choose_style(db, kind)}
                   for kind in ("sign", "plain") for style, rec in style_record(db, kind).items()],
        "sign_paused": not sign_worth_trying(db),
        "recent": [{
            "prompt_id": r.prompt_id, "created_at": r.created_at.isoformat() if r.created_at else None,
            "template_id": r.template_id, "kind": r.kind, "style": r.style, "scene": r.scene,
            "phrase": r.phrase, "prompt": r.prompt, "model": r.model, "seed": r.seed,
            "media_id": r.media_id, "checked": r.checked, "passed": r.passed,
            "gibberish": r.gibberish, "outcome": r.outcome, "note": r.note,
        } for r in rows],
    }


# ---------------------------------------------------------------------------
# The day's free image allowance, as the Studio shows it
# ---------------------------------------------------------------------------

# Hugging Face does not say how much of the free GPU allowance is left, so
# the images made are counted here against this number. 3 is what one free
# account got through on 2026-10-09 before "runs limit"; change it with
# STUDIO_DAILY_IMAGE_LIMIT (Hugging Face PRO allows far more).
DAILY_IMAGE_LIMIT = int(os.environ.get("STUDIO_DAILY_IMAGE_LIMIT", "3"))
WINDOW = timedelta(hours=24)
# When Hugging Face refused for want of allowance, and when it said to come back.
QUOTA_KEY = "studio_image_quota_until"


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def note_quota_spent(retry_after: Optional[int]) -> None:
    """
    Hugging Face refused for want of allowance: the Studio shows the limit as
    reached until it said to come back, or for an hour when it did not say.
    """
    from src.models import AppSetting

    until = datetime.now(timezone.utc) + (timedelta(seconds=retry_after) if retry_after else timedelta(hours=1))
    db = _session()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == QUOTA_KEY).first() or AppSetting(key=QUOTA_KEY)
        row.value = until.isoformat()
        db.merge(row)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("image_prompts event=QUOTA_NOTE_FAILED")
    finally:
        db.close()


def allowance(db: Session, now: Optional[datetime] = None) -> dict:
    """
    How many images can still be made today. The day is Hugging Face's: it
    starts with the first image and ends 24 hours later. A refusal from
    Hugging Face overrides the count, with the time it gave.
    """
    from src.models import AppSetting

    now = now or datetime.now(timezone.utc)
    made = [_utc(r.created_at) for r in db.query(StudioImagePrompt.created_at)
            .filter(StudioImagePrompt.created_at >= now - 2 * WINDOW, StudioImagePrompt.created_at <= now)
            .order_by(StudioImagePrompt.created_at)]
    # Hugging Face's days are not a rolling 24 hours: one starts with an image
    # and ends 24 hours later, and the next starts with the next image after.
    started = None
    for t in made:
        if started is None or t >= started + WINDOW:
            started = t
    if started is not None and now >= started + WINDOW:
        started = None
    used = sum(1 for t in made if started is not None and t >= started)
    resets_at = started + WINDOW if started else None
    remaining = max(0, DAILY_IMAGE_LIMIT - used)

    row = db.query(AppSetting).filter(AppSetting.key == QUOTA_KEY).first()
    refused_until = _utc(datetime.fromisoformat(row.value)) if row and row.value else None
    refused = bool(refused_until and refused_until > now)
    if refused:
        remaining, resets_at = 0, refused_until
    return {
        "limit": DAILY_IMAGE_LIMIT, "used": used, "remaining": remaining,
        "reached": remaining == 0, "refused_by_provider": refused,
        "window_started_at": started.isoformat() if started else None,
        "resets_at": resets_at.isoformat() if remaining == 0 and resets_at else None,
        "images_per_draft": 2,
    }
