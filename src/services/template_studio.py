"""
The template agent: writes state-specific WhatsApp templates, one variant per
idea, and learns from how earlier ones did.

A round works like this:

1. Rows are created at once in GENERATING, so the Studio shows placeholders
   while the slow part runs in the background.
2. The copy for every variant is written in one call, so the variants test
   different angles rather than rephrasing one. The prompt carries the
   standing brief, the templates already sent (same language first), how each
   has performed by state, and the reasons a reviewer gave for rejecting
   earlier drafts.
3. Each variant is validated — script, facts, lengths — and sent back once
   with its problems listed if it fails.
4. A photograph is generated with no text in it, checked by the model for
   stray lettering and an artificial look, and regenerated if it fails.
5. The poster is rendered around it (see poster_renderer) and the row moves to
   AWAITING_APPROVAL.

Nothing reaches Meta here. Only approve() submits, and only when a person
calls it.
"""
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import case, exists, func
from sqlalchemy.orm import Session

from src.models import Business, Location
from src.models.whatsapp import (
    WhatsAppButtonClick, WhatsAppCampaign, WhatsAppCampaignRecipient,
    WhatsAppLinkClick, WhatsAppTemplate, HUMAN_LINK_CLICK,
)
from src.services import creative_brief, poster_renderer
from src.services.gemini_client import GeminiClient, GeminiError

logger = logging.getLogger("gmap_scraper.template_studio")

MEDIA_DIR = os.path.join("data", "whatsapp_media")

GENERATING = "GENERATING"
AWAITING_APPROVAL = "AWAITING_APPROVAL"
GENERATION_FAILED = "GENERATION_FAILED"
REJECTED = "REJECTED_BY_REVIEWER"
# States in which an agent template exists only in the Studio: not submitted,
# not sendable, and kept out of the Templates list and the campaign picker.
DRAFT_STATUSES = (GENERATING, AWAITING_APPROVAL, GENERATION_FAILED, REJECTED)

MAX_VARIANTS = 4
PHOTO_ATTEMPTS = 3
BODY_LIMIT = 900
# Meta's own limits for button labels and the footer.
BUTTON_TEXT_LIMIT = 25
FOOTER_LIMIT = 60

POSTER_FIELDS = (
    "headline_line1", "headline_line2", "headline_highlight", "subline",
    "callout", "callout_highlight", "benefits_title", "cta",
    "opportunity_title", "opportunity_text", "sign_title", "bank_name",
    "phone_label", "web_label",
)


# ---------------------------------------------------------------------------
# What the agent learns from
# ---------------------------------------------------------------------------

def targeted_states(db: Session) -> List[dict]:
    """The states the locations list targets, with the language each is written in."""
    loc_counts = dict(
        db.query(Location.state, func.count(Location.location_id))
        .filter(Location.state.isnot(None)).group_by(Location.state).all()
    )
    biz_counts = dict(
        db.query(Business.state, func.count(Business.business_id))
        .filter(Business.state.isnot(None)).group_by(Business.state).all()
    )
    out = []
    for state in sorted(set(loc_counts) | set(biz_counts)):
        code = creative_brief.language_for_state(state)
        out.append({
            "state": state,
            "language_code": code,
            "language": creative_brief.LANGUAGES[code]["name"] if code else None,
            "locations": loc_counts.get(state, 0),
            "businesses": biz_counts.get(state, 0),
        })
    return out


def template_performance(db: Session) -> List[dict]:
    """
    How every template has done, overall and per recipient state.

    A recipient's state comes from the business with the same phone number,
    which is how audiences are selected in the first place. Delivered and read
    only exist since the webhook went live, so `tracked` says whether any
    delivery data exists at all — zero reads with no tracking is unknown, not
    a failure.
    """
    R = WhatsAppCampaignRecipient
    phone_state = (
        db.query(Business.phone.label("phone"), func.min(Business.state).label("state"))
        .filter(Business.phone.isnot(None)).group_by(Business.phone).subquery()
    )
    visited = exists().where(WhatsAppLinkClick.recipient_id == R.recipient_id, HUMAN_LINK_CLICK)
    tapped = exists().where(WhatsAppButtonClick.recipient_id == R.recipient_id)

    rows = (
        db.query(
            WhatsAppCampaign.template_id,
            phone_state.c.state,
            func.count(R.sent_at),
            func.count(R.delivered_at),
            func.count(R.read_at),
            func.sum(case((visited, 1), else_=0)),
            func.sum(case((tapped, 1), else_=0)),
        )
        .join(WhatsAppCampaign, WhatsAppCampaign.campaign_id == R.campaign_id)
        .outerjoin(phone_state, phone_state.c.phone == R.phone)
        .filter(WhatsAppCampaign.template_id.isnot(None))
        .group_by(WhatsAppCampaign.template_id, phone_state.c.state)
        .all()
    )

    templates = {t.template_id: t for t in db.query(WhatsAppTemplate).all()}
    by_template: dict = {}
    for template_id, state, sent, delivered, read, visitors, tappers in rows:
        t = templates.get(template_id)
        if t is None:
            continue
        entry = by_template.setdefault(template_id, {
            "template_id": template_id,
            "name": t.name,
            "origin": t.origin or "manual",
            "target_state": t.target_state,
            "language": _body_language(t),
            "angle": (t.generation or {}).get("angle"),
            "angle_key": (t.generation or {}).get("angle_key"),
            "sent": 0, "delivered": 0, "read": 0, "visitors": 0, "tappers": 0,
            "by_state": [],
        })
        stats = {"state": state or "Unknown", "sent": sent, "delivered": delivered,
                 "read": read, "visitors": int(visitors or 0), "tappers": int(tappers or 0)}
        entry["by_state"].append(stats)
        for k in ("sent", "delivered", "read", "visitors", "tappers"):
            entry[k] += stats[k]

    out = []
    for entry in by_template.values():
        entry["tracked"] = entry["delivered"] > 0
        base = entry["delivered"] or 0
        entry["read_rate"] = round(entry["read"] / base, 3) if base else None
        entry["response_rate"] = (
            round((entry["visitors"] + entry["tappers"]) / base, 3) if base else None
        )
        entry["by_state"].sort(key=lambda s: -s["sent"])
        out.append(entry)
    out.sort(key=lambda e: (-(e["response_rate"] or 0), -e["sent"]))
    return out


def _body_language(t: WhatsAppTemplate) -> Optional[str]:
    """
    The language a template is actually written in, judged by script.

    The registered code cannot be trusted for older templates: every Hindi one
    went to Meta as en_US.
    """
    counts = {
        code: len(re.findall(f"[{lang['range']}]", t.body or ""))
        for code, lang in creative_brief.LANGUAGES.items() if code != "mr"
    }
    code, n = max(counts.items(), key=lambda kv: kv[1])
    return code if n else (t.language_code or None)


def _reference_bodies(db: Session, language_code: str, limit: int = 4) -> List[str]:
    """Bodies of real templates, the state's own language first, test ones skipped."""
    rows = (
        db.query(WhatsAppTemplate)
        .filter(~WhatsAppTemplate.status.in_(DRAFT_STATUSES))
        .order_by(WhatsAppTemplate.created_at.desc())
        .all()
    )
    real = [t for t in rows if len(t.body or "") > 300]
    lang_of = {t.template_id: _body_language(t) for t in real}
    # Marathi shares Devanagari with Hindi, so a Hindi reference is the closest
    # there is until a Marathi template exists.
    wanted = "hi" if language_code == "mr" else language_code
    same = [t for t in real if lang_of[t.template_id] == wanted]
    other = [t for t in real if lang_of[t.template_id] != wanted]
    seen, out = set(), []
    for t in same + other:
        if t.body in seen:
            continue
        seen.add(t.body)
        out.append(t.body)
        if len(out) == limit:
            break
    return out


def _review_history(db: Session, state: str) -> dict:
    agent = (
        db.query(WhatsAppTemplate)
        .filter(WhatsAppTemplate.origin == "agent", WhatsAppTemplate.target_state == state)
        .order_by(WhatsAppTemplate.created_at.desc())
        .limit(40).all()
    )
    rejected = [
        {"angle": (t.generation or {}).get("angle"), "reason": t.review_note}
        for t in agent if t.status == REJECTED and t.review_note
    ][:10]
    approved = [(t.generation or {}).get("angle") for t in agent
                if t.reviewed_at and t.status not in DRAFT_STATUSES][:10]
    tried = [(t.generation or {}).get("angle") for t in agent if (t.generation or {}).get("angle")]
    tried_keys: dict = {}
    for t in agent:
        key = (t.generation or {}).get("angle_key")
        if key:
            tried_keys[key] = tried_keys.get(key, 0) + 1
    return {"rejected": rejected, "approved": [a for a in approved if a], "tried": tried,
            "tried_keys": tried_keys}


def assign_angles(count: int, tried_keys: dict) -> List[str]:
    """
    One distinct angle per variant, the least-tried for this state first.

    Chosen here rather than left to the model: asked only to differ, it wrote
    two variants on the same idea. Ties keep the menu's order.
    """
    menu = list(creative_brief.ANGLES)
    return sorted(menu, key=lambda k: (tried_keys.get(k, 0), menu.index(k)))[:count]


# ---------------------------------------------------------------------------
# Copy
# ---------------------------------------------------------------------------

def _copy_prompt(state: str, language_code: str, angles: List[str], brief: Optional[str],
                 references: List[str], performance: List[dict], history: dict) -> str:
    count = len(angles)
    lang = creative_brief.LANGUAGES[language_code]
    perf_lines = []
    for p in performance[:12]:
        per_state = "; ".join(
            f"{s['state']}: sent {s['sent']}, delivered {s['delivered']}, read {s['read']}, "
            f"link visits {s['visitors']}, button taps {s['tappers']}"
            for s in p["by_state"][:4]
        )
        perf_lines.append(
            f"- \"{p['name']}\" (language {p['language']}, origin {p['origin']}"
            f"{', angle ' + p['angle_key'] if p.get('angle_key') else ''}"
            f"{': ' + p['angle'] if p['angle'] else ''}): {per_state}"
            f"{'' if p['tracked'] else ' [no delivery tracking for this one — reads and taps unknown]'}"
        )

    icons = ", ".join(creative_brief.BENEFIT_ICONS)
    refs = "\n\n---\n\n".join(references) or "(none yet)"
    bullets = lambda items: "\n".join(f"- {i}" for i in items) or "- (none)"

    return f"""You are the copywriter for Eko's WhatsApp outreach. You write WhatsApp marketing templates, and the text for the poster image that heads each one, inviting people in {state} to become SBI Kiosk Operators with Eko.

Write {count} variant(s) in {lang['name']} ({lang['script']} script), in this order, each built around its own assigned angle — the single idea it bets on. The results will be compared per angle, so every part of a variant (headline, callout, body, photo) must serve its angle, and variants must not blur into each other:
{chr(10).join(f"{i}. {k}: {creative_brief.ANGLES[k]}" for i, k in enumerate(angles, 1))}

FACTS — the only claims allowed:
{bullets(creative_brief.FACTS)}

RULES:
{bullets(creative_brief.COPY_RULES)}

TEMPLATES ALREADY SENT (learn their tone and structure; do not copy them):
{refs}

HOW TEMPLATES HAVE PERFORMED (response = link visits + button taps):
{chr(10).join(perf_lines) or '- no campaign data yet'}

EARLIER VARIANTS FOR {state.upper()} (find a fresh way into the angle, do not reuse their wording): {'; '.join(history['tried']) or 'none'}
ANGLES A REVIEWER APPROVED: {'; '.join(history['approved']) or 'none'}
DRAFTS A REVIEWER REJECTED, AND WHY (avoid these mistakes):
{bullets([f"{r['angle']}: {r['reason']}" for r in history['rejected']])}
{f"{chr(10)}THIS ROUND'S BRIEF FROM THE TEAM: {brief}" if brief else ''}

Answer with JSON only, in this shape:
{{"variants": [{{
  "angle_key": "the key of the angle assigned to this variant",
  "angle": "one English sentence saying how this variant expresses its angle",
  "body": "the WhatsApp message in {lang['name']}, at most {BODY_LIMIT} characters, no URLs",
  "footer": "at most {FOOTER_LIMIT} characters, e.g. the equivalent of 'Team Eko'",
  "apply_button": "button label meaning 'Apply now', at most 20 characters",
  "callback_button": "button label meaning 'Call me back', at most 20 characters",
  "poster": {{
    "headline_line1": "first headline line, about 3 words",
    "headline_line2": "second headline line, about 3 words",
    "headline_highlight": "a phrase copied exactly from headline_line2 to colour yellow",
    "subline": "one sentence, at most 110 characters, naming Eko, SBI and Kiosk Operator / CSP",
    "callout": "one punchy sentence for a dark box, at most 80 characters",
    "callout_highlight": "a phrase copied exactly from callout to colour yellow",
    "benefits_title": "the equivalent of 'You will get', at most 18 characters",
    "benefits": [{{"icon": "one of: {icons}", "text": "at most 24 characters"}}, ... exactly 6],
    "cta": "the equivalent of 'Apply today', at most 22 characters",
    "opportunity_title": "at most 32 characters",
    "opportunity_text": "at most 110 characters",
    "sign_title": "'Customer Service Point' as written on SBI signboards in {lang['name']}",
    "bank_name": "'State Bank of India' as written in {lang['name']}",
    "phone_label": "the equivalent of 'Call / WhatsApp:', at most 24 characters",
    "web_label": "the equivalent of 'Apply now:', at most 24 characters"
  }},
  "photo_scene": "in English: who is in the photo and what is happening — the kiosk operator (age, gender, clothing typical of {state}) seated behind the counter with a laptop and a fingerprint scanner, serving one or two customers typical of {state} (for example taking a thumbprint, counting cash, handing over a passbook); the setting (village or small town); the mood that suits the angle. Not a phone or tablet demo. No text, signs or logos."
}}]}}"""


def _clean(variant: dict) -> dict:
    """
    Undoes escaping the model sometimes leaves in its JSON strings: a literal
    backslash-n reached a live body in testing, and WhatsApp would print it.
    """
    def fix(text):
        return text.replace("\\n", "\n").replace("\\t", " ").strip() if isinstance(text, str) else text

    for key in ("body", "footer", "apply_button", "callback_button"):
        variant[key] = fix(variant.get(key))
    poster = variant.get("poster") or {}
    for key in POSTER_FIELDS:
        poster[key] = fix(poster.get(key))
    for b in poster.get("benefits") or []:
        b["text"] = fix(b.get("text"))
    return variant


def validate_copy(variant: dict, language_code: str) -> List[str]:
    """Everything wrong with one variant; empty when it can be used."""
    errors = []
    poster = variant.get("poster") or {}
    body = variant.get("body") or ""

    for key in ("angle", "body", "footer", "apply_button", "callback_button", "photo_scene"):
        if not (variant.get(key) or "").strip():
            errors.append(f"{key} is missing")
    for key in POSTER_FIELDS:
        if not (poster.get(key) or "").strip():
            errors.append(f"poster.{key} is missing")

    if len(body) > BODY_LIMIT:
        errors.append(f"body is {len(body)} characters; the limit is {BODY_LIMIT}")
    if re.search(r"https?://|www\.|kiosk\.eko\.in", body):
        errors.append("body contains a URL; the Apply button carries the link")
    if "7291988625" not in body.replace(" ", ""):
        errors.append(f"body does not give the contact number {creative_brief.PHONE}")
    if "{{" in body:
        errors.append("body contains a {{placeholder}}; none are allowed")
    if len(variant.get("footer") or "") > FOOTER_LIMIT:
        errors.append(f"footer is longer than {FOOTER_LIMIT} characters")
    for key in ("apply_button", "callback_button"):
        if len(variant.get(key) or "") > BUTTON_TEXT_LIMIT:
            errors.append(f"{key} is longer than {BUTTON_TEXT_LIMIT} characters")

    benefits = poster.get("benefits") or []
    if len(benefits) != 6:
        errors.append(f"poster.benefits has {len(benefits)} items; exactly 6 are needed")
    for i, b in enumerate(benefits):
        if b.get("icon") not in creative_brief.BENEFIT_ICONS:
            errors.append(f"poster.benefits[{i}].icon '{b.get('icon')}' is not one of the allowed icons")
    if poster.get("headline_highlight") and poster.get("headline_highlight") not in (poster.get("headline_line2") or ""):
        errors.append("poster.headline_highlight is not a phrase from headline_line2")
    if poster.get("callout_highlight") and poster.get("callout_highlight") not in (poster.get("callout") or ""):
        errors.append("poster.callout_highlight is not a phrase from callout")

    # Script: everything a recipient reads must be in the state's script.
    texts = {"body": body, "footer": variant.get("footer"),
             "apply_button": variant.get("apply_button"),
             "callback_button": variant.get("callback_button")}
    texts.update({f"poster.{k}": poster.get(k) for k in POSTER_FIELDS if k not in ("headline_highlight", "callout_highlight")})
    texts.update({f"poster.benefits[{i}]": b.get("text") for i, b in enumerate(benefits)})
    for name, text in texts.items():
        # A footer may legitimately be just "Team Eko".
        for problem in creative_brief.script_problems(text or "", language_code,
                                                      require_script=name != "footer"):
            errors.append(f"{name} {problem}")
    return errors


def _unsupported_claims(client: GeminiClient, variant: dict) -> List[str]:
    """
    Claims in a variant that the allowed facts do not support.

    The script and length checks cannot read meaning; the first real round
    offered "cash deposit", which is not a service we list. A second, cold
    reading against the facts catches that kind of drift. If the check itself
    fails the variant is not held up for it — the reviewer still reads it.
    """
    texts = [variant.get("body") or ""]
    poster = variant.get("poster") or {}
    texts += [str(poster.get(k) or "") for k in POSTER_FIELDS]
    texts += [b.get("text") or "" for b in poster.get("benefits") or []]
    prompt = (
        "You are checking marketing copy for factual accuracy. The ONLY facts that may be claimed are:\n"
        + "\n".join(f"- {f}" for f in creative_brief.FACTS)
        + "\n\nGeneral encouragement, greetings and calls to action are fine. List every specific claim "
        "in the copy below — a service, number, benefit, promise or partner — that these facts do not "
        "support, and any earning phrased as a guarantee rather than an opportunity. Quote each in the "
        "copy's own words with a short English explanation.\n\nCOPY:\n" + "\n".join(t for t in texts if t)
        + '\n\nAnswer with JSON only: {"unsupported": ["<quote> — <why>", ...]} (an empty list when all is supported).'
    )
    try:
        found = client.generate_json(prompt, temperature=0.0).get("unsupported") or []
        return [str(x) for x in found][:8]
    except GeminiError as e:
        logger.warning(f"template_studio event=FACT_CHECK_SKIPPED reason={e}")
        return []


def _write_copy(client: GeminiClient, prompt: str, angles: List[str], language_code: str) -> List[dict]:
    data = client.generate_json(prompt)
    variants = (data.get("variants") if isinstance(data, dict) else None) or []
    if not variants:
        raise GeminiError("The copywriter returned no variants")

    fixed = []
    for angle_key, variant in zip(angles, variants):
        variant = _clean(variant)
        errors = validate_copy(variant, language_code)
        errors += [f"unsupported claim: {c}" for c in _unsupported_claims(client, variant)]
        if errors:
            # One repair round, with the problems spelled out and the angle
            # pinned — an unpinned repair drifted back to the round's first idea.
            repair = (
                f"{prompt}\n\nYou wrote this variant:\n{json.dumps(variant, ensure_ascii=False)}\n\n"
                f"It has these problems:\n" + "\n".join(f"- {e}" for e in errors) +
                f"\n\nKeep its angle ({angle_key}: {creative_brief.ANGLES[angle_key]}). "
                "Return the corrected variant in the same JSON shape, as {\"variants\": [ ... one item ... ]}."
            )
            again = _clean((client.generate_json(repair, temperature=0.4).get("variants") or [{}])[0])
            errors = validate_copy(again, language_code)
            errors += [f"unsupported claim: {c}" for c in _unsupported_claims(client, again)]
            variant = again
        # The assignment is authoritative, whatever key the model echoed.
        variant["angle_key"] = angle_key
        variant["_errors"] = errors
        fixed.append(variant)
    return fixed


# ---------------------------------------------------------------------------
# Photo
# ---------------------------------------------------------------------------

def photo_prompt(scene: str, state: str) -> str:
    return (
        f"A candid, unposed documentary photograph taken inside a small State Bank of India "
        f"customer service point (a bank kiosk run by a local shopkeeper) in {state}, India. "
        f"{scene} The kiosk operator sits behind a counter with a laptop, a fingerprint scanner "
        f"and a small receipt printer, serving a customer at the counter. "
        f"Shot on a 35mm lens at eye level in natural daylight, slight film grain, true-to-life "
        f"colours, real skin texture with pores and imperfections, ordinary everyday clothing, a "
        f"lived-in room with papers and cables. The people are in the centre of the frame; the "
        f"upper fifth of the frame is a plain painted wall and the lower quarter is the front of "
        f"the counter. Absolutely no text, letters, numbers, signs, posters, logos or watermarks "
        f"anywhere in the image. Not an illustration, not a 3D render, not glossy stock photography."
    )


PHOTO_CHECK = (
    "Inspect this image and answer with JSON only: "
    '{"has_text": true if ANY letters, numbers, signs, posters, logos or pseudo-writing are visible, '
    '"photorealistic": true only if an ordinary viewer would believe it is a real photograph, '
    '"operator_serving_customer": true if a person behind a counter is serving a customer, '
    '"anatomy_problems": true if any hand, face or body looks distorted, '
    '"issues": [short strings describing anything wrong]}'
)


def _photo_passes(check: dict) -> bool:
    return (not check.get("has_text") and check.get("photorealistic")
            and check.get("operator_serving_customer") and not check.get("anatomy_problems"))


def _make_photo(gemini: GeminiClient, scene: str, state: str):
    """
    Generates a photo using the available models, with multiple attempts if the image check fails.
    """
    used_prompt = photo_prompt(scene, state)
    
    last_photo = None
    last_mime = "image/jpeg"
    last_check = {"issues": ["generation failed"]}
    
    for attempt in range(PHOTO_ATTEMPTS):
        try:
            photo = gemini.generate_image(used_prompt)
            # HF API usually returns JPEG or PNG
            mime = "image/png" if photo.startswith(b"\x89PNG") else "image/jpeg"
            check = gemini.inspect_image(photo, mime, PHOTO_CHECK)
            
            last_photo = photo
            last_mime = mime
            last_check = check
            
            if _photo_passes(check):
                return photo, mime, used_prompt, check
        except Exception as e:
            logger.warning(f"Photo generation attempt {attempt + 1} failed: {e}")
            last_check = {"issues": [str(e)]}
            
    if last_photo is None:
        raise GeminiError(f"Failed to generate photo after {PHOTO_ATTEMPTS} attempts: {last_check.get('issues')}")
        
    return last_photo, last_mime, used_prompt, last_check


def _save_media(data: bytes, ext: str) -> str:
    os.makedirs(MEDIA_DIR, exist_ok=True)
    media_id = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(MEDIA_DIR, media_id), "wb") as fh:
        fh.write(data)
    return media_id


def _read_media(media_id: str) -> bytes:
    with open(os.path.join(MEDIA_DIR, os.path.basename(media_id)), "rb") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Assembling a template
# ---------------------------------------------------------------------------

def _apply_url() -> str:
    """
    Where the Apply button points. With a public base URL every recipient gets
    their own tracked link — the only way a tap on a URL button is counted,
    since Meta reports nothing for one.
    """
    base = (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
    if base:
        return f"{base}/r/{{{{1}}}}"
    return os.environ.get("CAMPAIGN_LINK_TARGET_URL", "https://kiosk.eko.in/signup?utm_source=AutoGMap")


def _render_into(tmpl: WhatsAppTemplate, poster: dict, photo: bytes, photo_mime: str) -> None:
    image = poster_renderer.render(poster, tmpl.language_code, photo, photo_mime)
    media_id = _save_media(image, ".jpg")
    tmpl.header_type = "IMAGE"
    tmpl.header_content = json.dumps({"source_type": "upload", "media_id": media_id})


def create_placeholders(db: Session, state: str, count: int, brief: Optional[str]) -> List[WhatsAppTemplate]:
    language_code = creative_brief.language_for_state(state)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    rows = []
    for _ in range(count):
        short = uuid.uuid4().hex[:5]
        t = WhatsAppTemplate(
            template_id=uuid.uuid4().hex,
            name=f"{state} Studio {stamp} {short}",
            language_code=language_code,
            category="MARKETING",
            body="",
            status=GENERATING,
            origin="agent",
            target_state=state,
            generation={"brief": brief},
        )
        db.add(t)
        rows.append(t)
    db.commit()
    return rows


def run_generation(template_ids: List[str], state: str, brief: Optional[str]) -> None:
    """Background entry point: fills the placeholder rows created for a round."""
    from src.database import SessionLocal

    db = SessionLocal()
    try:
        rows = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id.in_(template_ids)).all()
        language_code = creative_brief.language_for_state(state)
        client = GeminiClient()

        def fail_all(reason: str):
            for t in rows:
                if t.status == GENERATING:
                    t.status = GENERATION_FAILED
                    t.generation = {**(t.generation or {}), "error": reason}
            db.commit()

        try:
            history = _review_history(db, state)
            angles = assign_angles(len(rows), history["tried_keys"])
            prompt = _copy_prompt(
                state, language_code, angles, brief,
                _reference_bodies(db, language_code),
                template_performance(db),
                history,
            )
            variants = _write_copy(client, prompt, angles, language_code)
            models = {"text": client.text_model()}
        except Exception as e:
            logger.exception("template_studio event=COPY_FAILED")
            fail_all(str(e) if isinstance(e, GeminiError) else f"Copywriting failed: {e}")
            return

        for tmpl, variant in zip(rows, variants):
            try:
                # The copy is saved before the photo is attempted, so a photo
                # failure — no image quota, say — keeps the writing, and
                # "New photo" can finish the draft later.
                errors = variant.pop("_errors", [])
                tmpl.body = (variant.get("body") or "").strip()
                tmpl.footer = (variant.get("footer") or "").strip() or None
                tmpl.buttons = [
                    {"type": "URL", "text": (variant.get("apply_button") or "").strip(), "url": _apply_url()},
                    {"type": "QUICK_REPLY", "text": (variant.get("callback_button") or "").strip()},
                ]
                tmpl.generation = {
                    **(tmpl.generation or {}),
                    "angle": variant.get("angle"),
                    "angle_key": variant.get("angle_key"),
                    "poster": variant.get("poster"),
                    "photo_scene": variant.get("photo_scene"),
                    "copy_warnings": errors,
                    "models": models,
                }
                db.commit()

                photo, mime, used_prompt, check = _make_photo(client, variant["photo_scene"], state)
                photo_id = _save_media(photo, ".png" if mime == "image/png" else ".jpg")
                _render_into(tmpl, variant["poster"], photo, mime)
                tmpl.generation = {
                    **tmpl.generation,
                    "photo_prompt": used_prompt,
                    "photo_media_id": photo_id,
                    "photo_check": check,
                    "models": {**models, "image": client.last_used_image_model},
                }
                tmpl.status = AWAITING_APPROVAL
                db.commit()
                logger.info(f"template_studio event=DRAFT_READY template_id={tmpl.template_id} state={state}")
            except Exception as e:
                db.rollback()
                logger.exception(f"template_studio event=VARIANT_FAILED template_id={tmpl.template_id}")
                tmpl.status = GENERATION_FAILED
                tmpl.generation = {**(tmpl.generation or {}), "angle": variant.get("angle"),
                                   "angle_key": variant.get("angle_key"), "error": str(e)}
                db.commit()

        # Fewer variants came back than were asked for.
        fail_all("The copywriter returned fewer variants than requested")
    finally:
        db.close()


def run_new_photo(template_id: str) -> None:
    """Background entry point: a new photograph for a draft, same copy."""
    from src.database import SessionLocal

    db = SessionLocal()
    try:
        tmpl = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id == template_id).first()
        if not tmpl:
            return
        gen = dict(tmpl.generation or {})
        try:
            client = GeminiClient()
            photo, mime, used_prompt, check = _make_photo(client, gen["photo_scene"], tmpl.target_state)
            gen["photo_media_id"] = _save_media(photo, ".png" if mime == "image/png" else ".jpg")
            gen["photo_prompt"], gen["photo_check"] = used_prompt, check
            gen.setdefault("models", {})["image"] = client.last_used_image_model
            gen.pop("error", None)
            _render_into(tmpl, gen["poster"], photo, mime)
            tmpl.generation = gen
            tmpl.status = AWAITING_APPROVAL
        except Exception as e:
            logger.exception(f"template_studio event=PHOTO_FAILED template_id={template_id}")
            gen["error"] = str(e)
            tmpl.generation = gen
            tmpl.status = AWAITING_APPROVAL if tmpl.header_content else GENERATION_FAILED
        db.commit()
    finally:
        db.close()


def update_draft(db: Session, tmpl: WhatsAppTemplate, body: Optional[str], footer: Optional[str],
                 buttons: Optional[dict], poster: Optional[dict]) -> List[str]:
    """
    Applies a reviewer's edits and re-renders the poster when its text changed.
    Returns validation problems; the edit is saved either way, so a reviewer
    can knowingly keep wording the checker dislikes.
    """
    gen = dict(tmpl.generation or {})
    if body is not None:
        tmpl.body = body.strip()
    if footer is not None:
        tmpl.footer = footer.strip() or None
    if buttons:
        current = list(tmpl.buttons or [])
        for b in current:
            if b.get("type") == "URL" and buttons.get("apply_button"):
                b["text"] = buttons["apply_button"].strip()
            if b.get("type") == "QUICK_REPLY" and buttons.get("callback_button"):
                b["text"] = buttons["callback_button"].strip()
        tmpl.buttons = current
    if poster:
        merged = {**(gen.get("poster") or {}), **poster}
        photo = _read_media(gen["photo_media_id"])
        mime = "image/png" if photo[:4] == b"\x89PNG" else "image/jpeg"
        _render_into(tmpl, merged, photo, mime)
        gen["poster"] = merged
    tmpl.generation = gen
    db.commit()

    buttons_now = {b.get("type"): b.get("text") for b in (tmpl.buttons or [])}
    return validate_copy({
        "angle": gen.get("angle"), "body": tmpl.body, "footer": tmpl.footer or "",
        "apply_button": buttons_now.get("URL"), "callback_button": buttons_now.get("QUICK_REPLY"),
        "photo_scene": gen.get("photo_scene"), "poster": gen.get("poster") or {},
    }, tmpl.language_code)


def approve(db: Session, tmpl: WhatsAppTemplate, reviewer: str, category: str = "MARKETING") -> dict:
    """
    The reviewer's yes. This, and only this, submits an agent template to Meta.
    If Meta refuses the submission the draft stays awaiting approval, with the
    reason, so it can be edited and approved again.
    """
    from src.services.whatsapp_service import WhatsAppTemplateSubmissionService

    tmpl.reviewed_by = reviewer
    tmpl.reviewed_at = datetime.now(timezone.utc)
    tmpl.review_note = None
    db.commit()

    result = WhatsAppTemplateSubmissionService(db).submit(tmpl, category=category)
    db.refresh(tmpl)
    if result["status"] != "success":
        tmpl.status = AWAITING_APPROVAL
        db.commit()
    logger.info(
        f"template_studio event=DRAFT_APPROVED template_id={tmpl.template_id} by={reviewer} "
        f"submitted={result['status']}"
    )
    return result


def reject(db: Session, tmpl: WhatsAppTemplate, reviewer: str, reason: str) -> None:
    tmpl.status = REJECTED
    tmpl.review_note = reason.strip()
    tmpl.reviewed_by = reviewer
    tmpl.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(f"template_studio event=DRAFT_REJECTED template_id={tmpl.template_id} by={reviewer}")
