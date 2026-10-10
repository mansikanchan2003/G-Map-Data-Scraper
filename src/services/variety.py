"""
Keeps drafts from looking and reading alike.

Left to themselves the agents gave every draft the same poster structure, the
same kind of photo and messages built the same way, only reworded. Each
variant is now given, in code, the least-used of:

- a poster layout (poster_renderer.LAYOUTS),
- a camera shot and setting for the photo (SHOTS),
- an operator, a man or a woman (OPERATORS),
- a shape for the message (SHAPES),

and the writing model is shown the headlines and openings already used, with
the instruction to write something different in words and structure.
"""
from collections import Counter
from typing import Dict, List

from sqlalchemy.orm import Session

from src.models.whatsapp import WhatsAppTemplate

SHOTS: Dict[str, str] = {
    "wide_doorway": "a wide shot from the doorway showing the whole kiosk: the counter, the operator and two or "
                    "three customers, with the wall of posters behind",
    "over_shoulder": "over the shoulder of a customer standing at the counter, looking towards the operator, "
                     "who faces the camera",
    "side_counter": "a side view along the counter: the operator helping a customer with a fingerprint scan, "
                    "a short queue behind",
    "operator_close": "a medium close-up of the operator at work, smiling, the customer partly in the frame",
    "family_visit": "a family, parents and a child, at the counter while the operator explains a passbook",
    "busy_morning": "a busy morning at the kiosk: several customers at the counter, the operator serving one "
                    "of them",
}

OPERATORS: Dict[str, str] = {
    "woman": "The operator is a woman in a saree, kurti or salwar suit.",
    "man": "The operator is a man in a neat collared shirt or T-shirt.",
}

SHAPES: Dict[str, str] = {
    "question_led": "open with a question to the reader, then answer it",
    "checklist": "a short opening line, then a ✅ checklist of what they get, then how to apply",
    "three_steps": "show how to start in three numbered steps: apply, get trained, start serving",
    "earning_first": "lead with the earning opportunity, then the services, then how to apply",
    "community_first": "lead with the people of their area and what the kiosk does for them, then the "
                       "opportunity",
    "short_punchy": "three or four short, punchy lines, no list",
}


def _least_used(options: List[str], used: Counter, n: int) -> List[str]:
    """n options, the least used first; when there are more variants than options, round again."""
    ranked = sorted(options, key=lambda k: (used.get(k, 0), options.index(k)))
    return [ranked[i % len(ranked)] for i in range(n)]


def plan(db: Session, count: int) -> List[dict]:
    """What each variant of a round is given, by what recent drafts used least."""
    from src.services.poster_renderer import LAYOUTS

    recent = [t.generation or {} for t in db.query(WhatsAppTemplate)
              .filter(WhatsAppTemplate.origin == "agent")
              .order_by(WhatsAppTemplate.created_at.desc()).limit(60)]
    used = {k: Counter(g.get(k) for g in recent if g.get(k)) for k in ("layout", "shot", "operator", "shape")}
    layouts = _least_used(list(LAYOUTS), used["layout"], count)
    shots = _least_used(list(SHOTS), used["shot"], count)
    operators = _least_used(list(OPERATORS), used["operator"], count)
    shapes = _least_used(list(SHAPES), used["shape"], count)
    return [{"layout": layouts[i], "shot": shots[i], "operator": operators[i], "shape": shapes[i]}
            for i in range(count)]


def photo_direction(p: dict) -> str:
    """The shot and operator, as the image prompt states them."""
    shot = SHOTS.get(p.get("shot") or "")
    who = OPERATORS.get(p.get("operator") or "")
    return " ".join(x for x in ((f"Shot as {shot}." if shot else ""), who or "") if x)


def already_used(db: Session, language_code: str, limit: int = 10) -> dict:
    """Headlines and openings recent drafts in this language used, for the next to avoid."""
    rows = (db.query(WhatsAppTemplate)
            .filter(WhatsAppTemplate.origin == "agent", WhatsAppTemplate.language_code == language_code)
            .order_by(WhatsAppTemplate.created_at.desc()).limit(40).all())
    headlines, openings = [], []
    for t in rows:
        poster = (t.generation or {}).get("poster") or {}
        h = " / ".join(x for x in (poster.get("headline_line1"), poster.get("headline_line2")) if isinstance(x, str) and x)
        if h and h not in headlines:
            headlines.append(h)
        first = next((ln.strip() for ln in (t.body or "").splitlines() if ln.strip()), "")
        if first and first not in openings:
            openings.append(first[:120])
    return {"headlines": headlines[:limit], "openings": openings[:limit]}


def prompt_section(plans: List[dict], used: dict) -> str:
    """What the writing model is told about each variant's shape and photo, and what to avoid."""
    lines = [
        "MAKE EACH VARIANT DIFFERENT — not the same message reworded. Each has its own shape and its own photo:",
    ]
    for i, p in enumerate(plans, 1):
        lines.append(f"{i}. message shape: {SHAPES[p['shape']]}; photo: {SHOTS[p['shot']]}. "
                     f"{OPERATORS[p['operator']]} Write photo_scene to match.")
    if used.get("headlines"):
        lines.append("HEADLINES ALREADY USED — write headlines different from these in words and structure: "
                     + "; ".join(used["headlines"]))
    if used.get("openings"):
        lines.append("OPENING LINES ALREADY USED — open differently: " + "; ".join(used["openings"]))
    return "\n".join(lines)
