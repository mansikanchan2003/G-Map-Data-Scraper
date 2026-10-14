"""
The growth plan: how many leads we have against the goal, where people drop
out on the way to one, and what to do next to get more.

A LEAD is a person a campaign reached who submitted their documents. Revenue
comes from leads, so every campaign, template and audience is judged by how
it moves people towards one. The goal (LEAD_GOAL by LEAD_GOAL_DEADLINE) is
shown on the Campaign Insights page and given to the template agents, which
read this plan afresh each time they write, so what they make follows the
latest results.

Everything here is computed from what happened, through campaign_insights'
facts and the conversations, and labelled with how firm the evidence is.
Where the data is too thin to say what works, the plan says so and suggests
what to try, so the next campaigns also teach us something.
"""
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models import Business
from src.models.business import CONTACTABLE, NOT_PARTNER
from src.models.inbox import WhatsAppConversation
from src.models.location import Location
from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient
from src.services import campaign_insights as ci
from src.services import creative_brief, inbox

IST = ci.IST
LEAD_GOAL = int(os.environ.get("LEAD_GOAL", "10"))
LEAD_GOAL_DEADLINE = date.fromisoformat(os.environ.get("LEAD_GOAL_DEADLINE", "2026-10-31"))

# Steps of the way from a message to a lead, in order. Each counts people.
FUNNEL = [
    ("sent", "Messages sent"),
    ("delivered", "Delivered"),
    ("read", "Read"),
    ("engaged", "Replied or tapped"),
    ("interested", "Started applying"),
    ("area_ok", "PIN in our area"),
    ("education_ok", "12th pass or more"),
    ("can_invest", "Can invest ₹5 lakh"),
    ("link_sent", "Got the upload link"),
    ("lead", "Submitted documents (lead)"),
]

# What to do when most people are lost at a step: (step lost at, advice).
LEAKS = {
    "delivered": "Many messages are never delivered. Message mobile numbers only, do not message the same "
                 "people again within a week (Meta then holds marketing messages back), and keep the number's "
                 "quality rating green.",
    "read": "Delivered but not opened. The image and the first line decide whether a message is opened: "
            "lead with the earning and the SBI name, in the reader's own language.",
    "engaged": "Read but not answered. Make the ask plain and single: one clear reason to tap Interested.",
    "interested": "People write back but do not start applying. Answer their questions fast: clear the Needs "
                  "attention list in the Inbox the same day.",
    "area_ok": "Applicants are outside our areas. Message only businesses near our target PIN codes, or add "
               "the PIN codes people keep sending.",
    "education_ok": "Applicants are below 12th. Target categories run by educated owners (e.g. computer "
                    "centres, insurance and travel agents), and say \"12th pass\" in the template.",
    "can_invest": "Applicants cannot invest ₹5 lakh. Target established businesses with capital, and mention "
                  "the investment honestly in the template, so the ones who answer can afford it.",
    "link_sent": "People stop before the documents step. Call them: they are qualified and need a nudge.",
    "lead": "People got the upload link but have not submitted. Call each one today; offer to help with "
            "scanning or uploading.",
}


def today_ist() -> date:
    return datetime.now(IST).date()


def _last10(phone: Optional[str]) -> str:
    return re.sub(r"\D", "", phone or "")[-10:]


def real_campaign_ids(db: Session) -> set:
    tests = ci.test_campaign_ids(db)
    return {c.campaign_id for c in db.query(WhatsAppCampaign.campaign_id) if c.campaign_id not in tests}


team_phones = ci.team_phones


def _people(db: Session) -> List[WhatsAppConversation]:
    """Conversations with people a real campaign reached, the team's own left out."""
    reached = {inbox.normalize_phone(p) for (p,) in db.query(WhatsAppCampaignRecipient.phone)
               .filter(WhatsAppCampaignRecipient.campaign_id.in_(real_campaign_ids(db)),
                       WhatsAppCampaignRecipient.sent_at.isnot(None))}
    team = team_phones(db)
    # Only people who wrote back: the inbox also holds a thread for everyone
    # a campaign merely went to.
    return [c for c in db.query(WhatsAppConversation).all()
            if c.phone in reached and c.phone not in team
            and (c.last_inbound_at is not None or c.documents_submitted_at is not None)]


def goal(db: Session, people: Optional[List[WhatsAppConversation]] = None,
         facts: Optional[List[dict]] = None) -> dict:
    """Leads so far against the goal, and what it takes to reach it in time."""
    people = _people(db) if people is None else people
    leads = sorted((c for c in people if c.documents_submitted_at),
                   key=lambda c: inbox.aware(c.documents_submitted_at))
    have = len(leads)
    today = today_ist()
    days_left = max((LEAD_GOAL_DEADLINE - today).days + 1, 0)
    still = max(LEAD_GOAL - have, 0)
    sent = len(facts) if facts is not None else 0
    # Leads per message so far; with none yet, nothing can be projected.
    per_send = have / sent if sent and have else None
    return {
        "target": LEAD_GOAL,
        "deadline": LEAD_GOAL_DEADLINE.isoformat(),
        "leads": have,
        "still_needed": still,
        "days_left": days_left,
        "per_day_needed": round(still / days_left, 1) if days_left else None,
        "on_track": still == 0,
        "messages_sent": sent,
        "leads_per_1000": round(per_send * 1000, 2) if per_send else None,
        # At today's conversion, how many more messages the rest would take.
        "messages_needed": int(round(still / per_send)) if per_send and still else None,
        "lead_list": [{"name": c.profile_name, "phone": c.phone,
                       "submitted_at": inbox.aware(c.documents_submitted_at).isoformat()} for c in leads],
    }


def funnel(db: Session, people: List[WhatsAppConversation], facts: List[dict]) -> dict:
    """How many people reached each step, where most are lost, and what to do about it."""
    from src.services import applications
    from src.services import onboarding_bot as bot

    # People still to answer a step's question have not dropped out there.
    asked_at = {bot.CHOOSE_LANG: "area_ok", bot.AWAIT_PIN: "area_ok", bot.AWAIT_EDUCATION: "education_ok",
                bot.AWAIT_INVEST: "can_invest", bot.AWAIT_FRANCHISE: "can_invest",
                bot.AWAIT_DOCS: "link_sent", bot.AWAIT_UPLOAD: "lead"}
    waiting = Counter()
    count = {k: 0 for k, _ in FUNNEL}
    count["sent"] = len(facts)
    count["delivered"] = sum(f["delivered"] for f in facts)
    count["read"] = sum(f["read"] for f in facts)
    count["engaged"] = max(sum(f["engaged"] for f in facts), len(people))
    for c in people:
        data = c.bot_data or {}
        if not applications.is_application(c):
            continue
        count["interested"] += 1
        if c.bot_step in asked_at and not c.documents_submitted_at:
            waiting[asked_at[c.bot_step]] += 1
        q = applications.qualify(c)
        submitted = c.documents_submitted_at is not None
        if q["pin_qualified"] or submitted:
            count["area_ok"] += 1
            if data.get("education") in ("12", "grad") or submitted:
                count["education_ok"] += 1
                if data.get("can_invest") is True or submitted:
                    count["can_invest"] += 1
                    if c.upload_token or submitted:
                        count["link_sent"] += 1
                        if submitted:
                            count["lead"] += 1

    # Campaigns sent before delivery reports were recorded have almost none,
    # which is not the same as not delivered (a few came in later). Delivery
    # is measured on campaigns begun after the first report arrived.
    first_report = min((f["report_time"] for f in facts if f.get("report_time")), default=None)
    started = {}
    for f in facts:
        started[f["campaign_id"]] = min(started.get(f["campaign_id"], f["sent_time"]), f["sent_time"])
    reporting = {c for c, at in started.items() if first_report and at >= first_report}
    tracked = [f for f in facts if f["campaign_id"] in reporting]
    tracked_sent = len(tracked)
    count["delivered"] = sum(f["delivered"] for f in tracked)
    count["read"] = sum(f["read"] for f in tracked)

    steps = []
    prev = None
    for key, label in FUNNEL:
        n = count[key]
        base = tracked_sent if key == "delivered" else prev
        rate = n / base if base else None
        if key in waiting and prev:
            # Measured on those who have answered; the rest are still deciding.
            decided = prev - waiting[key]
            rate = n / decided if decided > 0 else None
        steps.append({"key": key, "label": label, "count": n,
                      "from_previous": round(rate, 3) if rate is not None else None,
                      "waiting": waiting.get(key, 0),
                      **({"of_tracked": tracked_sent} if key == "delivered" else {})})
        prev = n or prev
    # The biggest leak among steps with enough people to tell, after delivery.
    leak = None
    for i in range(1, len(steps)):
        before, step = steps[i - 1], steps[i]
        if before["count"] < 3 or step["from_previous"] is None:
            continue
        # Fewer people at a step than at a later one means it is not fully
        # recorded (a read receipt turned off, say), not that people left.
        if step["count"] < max(s["count"] for s in steps[i + 1:] or [step]):
            continue
        lost = 1 - step["from_previous"]
        frm = step.get("of_tracked", before["count"] - step["waiting"])
        if frm < 3:
            continue
        if step["key"] in LEAKS and (leak is None or lost > leak["lost"]):
            leak = {"step": step["key"], "label": step["label"], "lost": round(lost, 3),
                    "from": frm, "to": step["count"], "advice": LEAKS[step["key"]]}
    return {"steps": steps, "biggest_leak": leak}


def warm_people(people: List[WhatsAppConversation]) -> List[dict]:
    """
    People part-way to a lead: the quickest leads there are. A call or a
    message from the team turns many of them into one.
    """
    from src.services import applications
    from src.services import onboarding_bot as bot

    order = {bot.AWAIT_UPLOAD: 0, bot.AWAIT_DOCS: 1, bot.AWAIT_INVEST: 2, bot.AWAIT_EDUCATION: 3,
             bot.AWAIT_PIN: 4, bot.CHOOSE_LANG: 5, bot.WEBINAR_CONFIRMED: 6, bot.WEBINAR_AVAILABILITY: 6,
             bot.AWAIT_WEBINAR: 7, bot.AWAIT_AVAILABILITY: 7}
    out = []
    for c in people:
        if c.documents_submitted_at or c.bot_step not in order:
            continue
        if applications.qualify(c)["not_qualified"]:
            continue
        out.append({"name": c.profile_name, "phone": c.phone,
                    "stage": bot.STEP_LABELS.get(c.bot_step, c.bot_step),
                    "last_message_at": inbox.aware(c.last_message_at).isoformat() if c.last_message_at else None,
                    "_rank": order[c.bot_step]})
    out.sort(key=lambda p: (p["_rank"], p["last_message_at"] or ""))
    for p in out:
        p.pop("_rank")
    return out


def _untapped(db: Session) -> Dict[str, Counter]:
    """Businesses with a mobile number that no campaign has messaged yet, by district and category."""
    messaged = {_last10(p) for (p,) in db.query(WhatsAppCampaignRecipient.phone)}
    by_district, by_category, by_pair = Counter(), Counter(), Counter()
    rows = (db.query(Business.phone, Business.district, Business.state, Business.category)
            .filter(Business.is_valid.is_(True), CONTACTABLE, NOT_PARTNER, Business.phone.isnot(None)))
    seen = set()
    for phone, district, state, category in rows:
        d = _last10(phone)
        if len(d) != 10 or d[0] not in "6789" or d in messaged or d in seen:
            continue
        seen.add(d)
        place = district or "Unknown"
        by_district[place] += 1
        by_category[category] += 1
        by_pair[(place, category)] += 1
    return {"district": by_district, "category": by_category, "pair": by_pair}


def _ranked(book: dict, dim: str) -> List[dict]:
    rows = ci.aggregate(book["_facts"], (dim,), outcome=book["judged_on"])
    return [r for r in rows if not ci.is_unknown(r["values"][dim])]


def targets(db: Session, book: dict) -> dict:
    """Where to send next and to whom: what worked so far, and the reachable people left there."""
    pool = _untapped(db)
    stage = book["judged_on"]

    def rows_for(dim: str, key_of, pool_counter: Counter) -> List[dict]:
        done = {}
        for r in _ranked(book, dim):
            name = r["values"][dim]
            done[name] = {
                "name": name, "sent": r["sent"], "success": r["success"],
                "rate": r["success_rate"], "confidence": r["confidence"], "direction": r["direction"],
                "left": pool_counter.get(key_of(name), 0),
            }
        # Somewhere that answered, with people left, first; then the biggest
        # untried pools, so new campaigns also teach us something.
        tried = sorted(done.values(), key=lambda x: (-(x["success"] > 0), -x["rate"], -x["left"]))
        untried = [{"name": k, "sent": 0, "success": 0, "rate": None, "confidence": "untried",
                    "direction": "none", "left": n}
                   for k, n in pool_counter.most_common(40) if k not in done and k != "Unknown"][:8]
        return tried[:8] + untried

    return {
        "judged_on": stage,
        "districts": rows_for("district", lambda name: name, pool["district"]),
        "categories": rows_for("category", lambda name: name, pool["category"]),
        "best_pairs": [{"district": d, "category": c, "left": n} for (d, c), n in pool["pair"].most_common(10)],
        "reachable_left": sum(pool["district"].values()),
    }


def _showcase(book: dict) -> Optional[dict]:
    """The template that moved the most people, with its creative, if any moved."""
    rows = [r for r in _ranked(book, "template") if r["success"] and r["sent"] >= 10]
    if not rows:
        return None
    best = max(rows, key=lambda r: (r["success_rate"], r["sent"]))
    fact = next(f for f in book["_facts"] if f["template"] == best["values"]["template"])
    from src.models.whatsapp import WhatsAppTemplate

    db = book.get("_db")
    t = (db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id == fact["template_id"]).first()
         if db is not None and fact["template_id"] else None)
    header, body = (t.header_content, t.body) if t else (None, None)
    return {
        "template": best["values"]["template"], "sent": best["sent"], "success": best["success"],
        "rate": best["success_rate"], "confidence": best["confidence"], "direction": best["direction"],
        "header_content": header, "body": (body or "")[:400],
        "recipe": {k: fact[k] for k in ("angle", "layout", "image_headline", "language", "time_of_day", "weekday")},
    }


CREATIVE_DIMS = ("angle", "layout", "image_headline", "header", "body_length", "language_match",
                 "time_of_day", "weekday")


def creative(book: dict) -> dict:
    """What the templates that moved people had in common, and what is untried."""
    from src.services.poster_renderer import LAYOUTS

    campaigns: Dict[tuple, set] = {}
    for f in book["_facts"]:
        for dim in CREATIVE_DIMS:
            campaigns.setdefault((dim, f[dim]), set()).add(f["campaign_id"])

    out = {}
    for dim in CREATIVE_DIMS:
        rows = [r for r in _ranked(book, dim) if r["sent"] >= 10]
        out[dim] = [{"value": r["values"][dim], "sent": r["sent"], "success": r["success"],
                     "rate": r["success_rate"], "confidence": r["confidence"], "direction": r["direction"],
                     # One campaign is one place, one time and one template at
                     # once: which of them made the difference cannot be told.
                     "campaigns": len(campaigns.get((dim, r["values"][dim]), ()))}
                    for r in rows[:6]]
    used_angles = {r["value"] for r in out["angle"]}
    used_layouts = {r["value"].lower() for r in out["layout"]}
    out["showcase"] = _showcase(book)
    out["untried_angles"] = [k.replace("_", " ") for k in creative_brief.ANGLES
                             if k.replace("_", " ") not in used_angles][:6]
    out["untried_layouts"] = [l for l in LAYOUTS if l not in used_layouts]
    return out


def next_steps(g: dict, f: dict, warm: List[dict], t: dict, c: dict, book: dict) -> List[dict]:
    """What to do now, most effective first."""
    steps = []
    if warm:
        names = ", ".join(p["name"] or p["phone"] for p in warm[:5])
        steps.append({
            "icon": "call",
            "title": f"Call the {len(warm)} people already part-way to applying",
            "detail": f"They are qualified so far and stopped mid-way ({names}{'…' if len(warm) > 5 else ''}). "
                      "A call or a WhatsApp message from the team is the quickest way to a lead.",
            "why": "Every lead so far came from someone who started applying; these people already have.",
            "impact": "high",
        })
    if f["biggest_leak"]:
        leak = f["biggest_leak"]
        steps.append({
            "icon": "trending_down",
            "title": f"Fix the biggest drop: {leak['label'].lower()}",
            "detail": leak["advice"],
            "why": f"Only {leak['to']} of {leak['from']} people get past this step "
                   f"({(1 - leak['lost']) * 100:.0f}%).",
            "impact": "high",
        })
    good_places = [d for d in t["districts"] if d["success"] and d["left"]]
    if good_places:
        top = good_places[:3]
        steps.append({
            "icon": "location_on",
            "title": "Send next to the places that answered",
            "detail": "; ".join(f"{d['name']}: {d['success']} of {d['sent']} reached went on, "
                                f"{d['left']} businesses not yet messaged" for d in top),
            "why": f"Judged on “{ci.STAGE_LABELS[t['judged_on']].lower()}”; "
                   + ("evidence is still thin." if all(d["confidence"] in ("too_early", "no_difference") for d in top)
                      else "the difference is backed by the numbers."),
            "impact": "medium",
        })
    good_cats = [x for x in t["categories"] if x["success"] and x["left"]]
    if good_cats:
        steps.append({
            "icon": "storefront",
            "title": "Target the categories that answered",
            "detail": "; ".join(f"{x['name']}: {x['success']} of {x['sent']}, {x['left']} left" for x in good_cats[:4]),
            "why": "These owners responded; more of the same kind are waiting.",
            "impact": "medium",
        })
    untried = [x for x in t["categories"] if x["confidence"] == "untried"][:3]
    if untried:
        steps.append({
            "icon": "science",
            "title": "Test new categories in small batches",
            "detail": "Send 50–100 messages each to " + ", ".join(f"{x['name']} ({x['left']} available)" for x in untried)
                      + " to learn whether they answer.",
            "why": "Most categories were never messaged, so we cannot tell yet which convert best.",
            "impact": "medium",
        })
    if c["untried_angles"] or c["untried_layouts"]:
        steps.append({
            "icon": "palette",
            "title": "Try a new kind of template",
            "detail": ("Angles not used yet: " + ", ".join(c["untried_angles"][:4]) + ". " if c["untried_angles"] else "")
                      + ("Poster layouts not used yet: " + ", ".join(c["untried_layouts"]) + "." if c["untried_layouts"] else ""),
            "why": "With so few results, varying the creative is how we find out what draws leads.",
            "impact": "medium",
        })
    if g["still_needed"] and g["messages_needed"]:
        steps.append({
            "icon": "send",
            "title": f"Send about {g['messages_needed']:,} more messages, or convert better",
            "detail": f"At today's rate ({g['leads_per_1000']} leads per 1,000 messages) the remaining "
                      f"{g['still_needed']} leads need about {g['messages_needed']:,} messages in {g['days_left']} days.",
            "why": "Volume alone is slow; the steps above raise the rate.",
            "impact": "low",
        })
    return steps


def plan(db: Session) -> dict:
    """The whole plan: goal, funnel, warm people, targets, creative lessons and next steps."""
    facts = ci.load_facts(db)
    book = ci.playbook(db, facts)
    book["_facts"] = facts
    book["_db"] = db
    people = _people(db)
    g = goal(db, people, facts)
    f = funnel(db, people, facts)
    warm = warm_people(people)
    t = targets(db, book)
    c = creative(book)
    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "goal": g,
        "funnel": f,
        "warm_people": warm,
        "judged_on": book["judged_on"],
        "judged_on_label": book["judged_on_label"],
        "stages": book["stages"],
        "targets": t,
        "creative": c,
        "next_steps": next_steps(g, f, warm, t, c, book),
    }


def agent_brief(db: Session) -> str:
    """The plan, told to a template agent: the goal and what to write for it."""
    try:
        p = plan(db)
    except Exception:
        import logging
        logging.getLogger("gmap_scraper.growth_plan").exception("growth_plan event=BRIEF_FAILED")
        return ""
    g, c = p["goal"], p["creative"]

    def lines(dim: str, label: str) -> str:
        rows = c.get(dim) or []
        if not rows:
            return f"- {label}: no results yet"
        return f"- {label}: " + "; ".join(
            f"“{r['value']}” {r['success']} of {r['sent']} ({verdict(r)}"
            f"{', one campaign only: could be its place or timing' if r['campaigns'] == 1 else ''})"
            for r in rows[:4])

    def verdict(r: dict) -> str:
        if r["confidence"] in ("strong", "likely") and r["direction"] in ("better", "worse"):
            return f"{'proven' if r['confidence'] == 'strong' else 'likely'} {r['direction']} than the rest"
        return r["confidence"].replace("_", " ")

    leak = p["funnel"]["biggest_leak"]
    return f"""THE GOAL — read this first. Eko earns from LEADS: business owners who tap Interested, qualify (PIN in our area, 12th pass or more, can invest ₹5 lakh) and submit their documents. Target: {g['target']} leads by {g['deadline']}; we have {g['leads']}, with {g['days_left']} days left. A template that gets many replies from people who cannot qualify does not help. Write to win QUALIFIED owners: established shops and agencies with capital and an educated owner, and be honest that it is an investment-backed business.

WHAT MOVED PEOPLE SO FAR (judged on “{p['judged_on_label']}”, the furthest step with enough data; 'too early' means not proven yet):
{lines('angle', 'Message angle')}
{lines('layout', 'Poster layout')}
{lines('image_headline', 'Image headline')}
{lines('language_match', 'Language')}
{lines('body_length', 'Message length')}
WHERE PEOPLE DROP OUT: {(leak['label'] + ' — ' + leak['advice']) if leak else 'not enough data yet'}
NOT TRIED YET (worth testing): angles {', '.join(c['untried_angles'][:4]) or 'none'}; layouts {', '.join(c['untried_layouts']) or 'none'}.
Build on what moved people, avoid what did not, and when nothing is proven, make this template different from the ones above so it teaches us something. Every word on the image must be spelled correctly in its script, short, and readable at a glance."""
