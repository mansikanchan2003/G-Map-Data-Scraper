"""
Handing a chat between the bot and a person, and recording how it ended.

Agent to Human: a person takes a chat over by pressing "Take over" or simply
by replying in the inbox. The bot then stays quiet in that chat, and the
inbox shows who is handling it and since when.

Human to Agent: "Hand back to the bot" lets the bot carry on. The person
records the chat's disposition as they hand it back, any open ticket is
solved, and the bot asks again, in the person's language and with its
buttons, the question it was waiting on, so the applicant carries on where
they left off.

A disposition is the chat's outcome: Interested, Call back later, Not
reachable and so on. Every chat always has one: the one the team last
recorded, or, when the bot has moved the chat on since, the one its step
says (documents submitted, not eligible, outside our area...). Each one
recorded is kept in chat_activity with who and when, for the Dispositions tab.

The dispositions themselves, and what each one sets in motion, are the
team's sheet (dispositions.py); recording one plans its follow-ups
(followups.py).
"""
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.inbox import ChatActivity, WhatsAppConversation
from src.services import dispositions as dz, inbox, tickets
from src.services import onboarding_bot as bot

# Key: (label, group), every sub-category of the sheet. Groups colour them.
DISPOSITIONS: Dict[str, tuple] = {k: (v.label, dz.CATEGORY[v.category].group) for k, v in dz.SUBS.items()}

# The outcome the bot's own step stands for.
_FROM_STEP = {
    bot.SUBMITTED: "int_visit",
    bot.AWAIT_UPLOAD: "int_docs_pending",
    bot.AWAIT_DOCS: "int_docs_pending",
    bot.NOT_ELIGIBLE: "rej_eligibility",
    bot.NOT_SERVED: "int_not_sbi",
    bot.NOT_INVESTING: "ni_investment",
    bot.GUIDANCE_QA: "int_more_info",
    bot.AWAIT_WEBINAR: "int_more_info",
    bot.AWAIT_AVAILABILITY: "int_more_info",
    bot.WEBINAR_CONFIRMED: "int_more_info",
    bot.WEBINAR_AVAILABILITY: "int_more_info",
    bot.HANDOVER: "busy_later",
}


def label(key: Optional[str]) -> Optional[str]:
    return dz.label(key)


def options() -> List[dict]:
    return dz.options()


# The call outcomes a WhatsApp chat shows by itself (the user, 2026-11-06): what
# became of our last message, campaign or nudge, that they never answered.
#   failed to deliver          -> Number not reachable
#   delivered, never read      -> Ringing but not picked
#   read, no reply             -> No answer
# Only for a chat that is not moving: one still before the bot's questions, or
# stopped in them. A chat at a clearer step (documents pending, not eligible...)
# keeps that step's outcome, and anything the team recorded comes first.
UNANSWERED_FOR = timedelta(hours=24)
_REACH_STATUS = {"FAILED": "unr_not_reachable", "SENT": "rnr_not_picked", "DELIVERED": "rnr_not_picked",
                 "READ": "rnr_no_answer"}


def reach_keys(db: Session, phones: Optional[List[str]] = None, at: Optional[datetime] = None) -> Dict[str, str]:
    """{phone: RNR or Unreachable outcome} for chats whose last message from us went unanswered."""
    from src.models.whatsapp import WhatsAppCampaignRecipient
    from src.models.inbox import WhatsAppMessage

    at = at or inbox.now()
    last: Dict[str, tuple] = {}

    def keep(phone, when, status):
        when = inbox.aware(when)
        if phone and when and status and (phone not in last or when > last[phone][0]):
            last[phone] = (when, status.upper())

    q = db.query(WhatsAppMessage.phone, WhatsAppMessage.created_at, WhatsAppMessage.status).filter(
        WhatsAppMessage.direction == "OUT")
    r = db.query(WhatsAppCampaignRecipient.phone, WhatsAppCampaignRecipient.sent_at,
                 WhatsAppCampaignRecipient.failed_at, WhatsAppCampaignRecipient.status).filter(
        WhatsAppCampaignRecipient.status.in_(("SENT", "DELIVERED", "READ", "FAILED")))
    if phones is not None:
        q = q.filter(WhatsAppMessage.phone.in_(phones))
        r = r.filter(WhatsAppCampaignRecipient.phone.in_(phones))
    for phone, when, status in q:
        keep(phone, when, status)
    for phone, sent, failed, status in r:
        keep(inbox.normalize_phone(phone), sent or failed, status)

    convs = db.query(WhatsAppConversation.phone, WhatsAppConversation.last_inbound_at)
    if phones is not None:
        convs = convs.filter(WhatsAppConversation.phone.in_(phones))
    out = {}
    for phone, inbound in convs:
        if phone not in last:
            continue
        when, status = last[phone]
        inbound = inbox.aware(inbound)
        if inbound and inbound >= when:
            continue                      # they wrote after it: answered
        key = _REACH_STATUS.get(status)
        if key and (status == "FAILED" or at - when >= UNANSWERED_FOR):
            out[phone] = key
    return out


def _reach_of(conv: WhatsAppConversation) -> Optional[str]:
    from sqlalchemy.orm import object_session
    db = object_session(conv)
    return reach_keys(db, [conv.phone]).get(conv.phone) if db is not None else None


def bot_disposition(conv: WhatsAppConversation, reach: Optional[str] = None) -> str:
    """What the chat's state says, without the team: from the bot's step, or an enquiry."""
    key = _step_disposition(conv)
    if (key == "other" and (conv.bot_data or {}).get("campaign")) or key == "int_in_bot_flow":
        if reach is None:
            reach = _reach_of(conv)
        if reach:
            return reach
    return key


def _step_disposition(conv: WhatsAppConversation) -> str:
    if conv.documents_submitted_at:
        # Documents in: AutoGMap's part is done and Eko Acquisition takes over.
        return "int_visit"
    if conv.bot_step in _FROM_STEP:
        return _FROM_STEP[conv.bot_step]
    if conv.bot_step and ((conv.bot_data or {}).get("coverage") or {}).get("served") is False:
        return "int_not_sbi"
    if conv.bot_step:
        return "int_in_bot_flow"
    # A campaign's chat that has not started the questions (their shop's
    # auto-reply, say) is not an enquiry of their own.
    return "other" if (conv.bot_data or {}).get("campaign") else "enquiry"


def current(conv: WhatsAppConversation, reach: Optional[Dict[str, str]] = None) -> dict:
    """
    The chat's disposition now: the team's, unless the bot has moved the chat
    on since it was recorded (or the documents came in), then the bot's.
    """
    team_at = inbox.aware(conv.disposition_at)
    moved = max(filter(None, [inbox.aware(conv.bot_updated_at), inbox.aware(conv.documents_submitted_at)]), default=None)
    if conv.disposition and team_at and not (moved and moved > team_at):
        key = dz.normalise(conv.disposition)
        return {"key": key, "label": label(key), "category": dz.category_of(key).key if dz.category_of(key) else None,
                "note": conv.disposition_note,
                "by": conv.disposition_by, "at": team_at.isoformat(), "source": "team"}
    key = bot_disposition(conv, (reach.get(conv.phone) or "") if reach is not None else None)
    return {"key": key, "label": label(key), "category": dz.category_of(key).key, "note": None, "by": "bot",
            "at": (moved or inbox.aware(conv.last_message_at) or inbox.aware(conv.created_at) or inbox.now()).isoformat(),
            "source": "bot"}


def _log(db: Session, conv: WhatsAppConversation, kind: str, by: str, value: str = None, note: str = None) -> ChatActivity:
    row = ChatActivity(activity_id=uuid.uuid4().hex, phone=conv.phone, kind=kind, value=value,
                       note=(note or "").strip()[:500] or None, by=by, at=inbox.now())
    db.add(row)
    return row


def record(db: Session, conv: WhatsAppConversation, key: str, by: str, note: Optional[str] = None,
           at: Optional[datetime] = None, attempt: int = 1, run_now: bool = True, ticket: bool = True,
           tell: bool = True) -> dict:
    """
    Record the chat's disposition and plan what it calls for. `at` is the
    time to call back or the date to follow up on, for those that ask.
    `tell=False` when the team has already been told (the bot's own
    escalation email), so they are not emailed twice.
    """
    from src.services import followups

    key = dz.normalise(key)
    if key not in DISPOSITIONS:
        raise ValueError(f"Unknown disposition: {key}")
    if by not in ("bot", "ai_call"):
        # A person's disposition judges the bot's reading of their reply (agent_telemetry).
        from src.services import agent_telemetry
        agent_telemetry.disposition_overridden(db, conv.phone, key, by)
    conv.disposition, conv.disposition_by, conv.disposition_at = key, by, inbox.now()
    conv.disposition_note = (note or "").strip()[:500] or None
    _log(db, conv, "disposition", by, key, note)
    followups.plan(db, conv, key, by, at=at, attempt=attempt, run_now=run_now, note=note, ticket=ticket, tell=tell)
    from src.services import opt_out
    if key in opt_out.OPT_OUT_DISPOSITIONS:
        # Not marketed to again; the disposition's own closing message still goes.
        opt_out.record(db, conv.phone, opt_out.DISPOSITION, by, reason=DISPOSITIONS[key][0])
    return current(conv)


def take_over(db: Session, conv: WhatsAppConversation, by: str) -> None:
    """Agent to Human: the bot stops answering here and the chat shows who is handling it."""
    if conv.bot_paused and conv.handled_by == by:
        return
    conv.bot_paused = True
    conv.handled_by, conv.handled_since = by, inbox.now()
    _log(db, conv, "to_person", by)


def hand_back(db: Session, conv: WhatsAppConversation, by: str, disposition: Optional[str] = None,
              note: Optional[str] = None, resume: bool = True, at: Optional[datetime] = None) -> Optional[str]:
    """
    Human to Agent: the bot carries on. Records the disposition, solves an open
    ticket, and asks again the question the bot was waiting on. Returns what
    the bot sent, or None when there was nothing to ask or the window is shut.
    """
    if disposition:
        # The bot carrying on asks its question; a nudge due now would be a second message.
        carries_on = resume and inbox.window_open(conv) and bot.pending_question(db, conv) is not None
        # The person handing back is the one handling it: the team is emailed, no new ticket opens.
        record(db, conv, disposition, by, note, at=at, run_now=not carries_on, ticket=False)
        if carries_on:
            _bot_carries_on(db, conv)
    conv.bot_paused = False
    conv.handled_by = conv.handled_since = None
    _log(db, conv, "to_bot", by, disposition, note if not disposition else None)
    if conv.needs_attention:
        conv.needs_attention = False
        conv.attention_resolved_by, conv.attention_resolved_at = by, inbox.now()
        tickets.resolve(db, conv.phone, by)
    if not resume or not inbox.window_open(conv):
        return None
    asked = bot.pending_question(db, conv)
    if not asked:
        return None
    question, opts = asked
    body = f"{bot._t(db, conv, 'resume')}\n\n{question}"
    inbox.send(db, conv.phone, body, sent_by="bot", **opts)
    return body


def _bot_carries_on(db: Session, conv: WhatsAppConversation) -> None:
    """The bot asks its own question instead of a nudge due now: one message, not two."""
    from src.models.inbox import FollowUp

    for f in db.query(FollowUp).filter(FollowUp.phone == conv.phone, FollowUp.status.in_(("scheduled", "waiting")),
                                       FollowUp.wants != dz.TASK, FollowUp.due_at <= inbox.now()).all():
        f.status, f.note, f.done_at = "cancelled", "The bot carried on with the chat instead", inbox.now()


def activity(db: Session, phone: str) -> List[dict]:
    rows = db.query(ChatActivity).filter(ChatActivity.phone == phone).order_by(ChatActivity.at).all()
    return [as_dict(r) for r in rows]


def as_dict(r: ChatActivity) -> dict:
    return {"kind": r.kind, "value": r.value, "label": label(r.value), "note": r.note, "by": r.by,
            "at": inbox.aware(r.at).isoformat() if r.at else None}


def who(email: Optional[str]) -> str:
    """kavya.shukla@eko.co.in -> Kavya Shukla."""
    if not email or "@" not in email:
        return email or "the team"
    return email.split("@")[0].replace(".", " ").replace("_", " ").title()


def dashboard(db: Session, days: int = 7) -> dict:
    """Every chat's disposition now, the team's recent ones, and who is handling what."""
    convs = db.query(WhatsAppConversation).all()
    reach = reach_keys(db)
    now = [current(c, reach) for c in convs]
    by_key = Counter(d["key"] for d in now)
    since = inbox.now() - timedelta(days=days)
    recent = (db.query(ChatActivity, WhatsAppConversation)
              .join(WhatsAppConversation, WhatsAppConversation.phone == ChatActivity.phone)
              .filter(ChatActivity.kind == "disposition", ChatActivity.at >= since)
              .order_by(ChatActivity.at.desc()).all())
    team_counts = Counter(dz.normalise(a.value) for a, _ in recent)
    handled = [c for c in convs if c.bot_paused and c.handled_by]
    # Outcomes the team recorded each day (IST), every day of the range shown, and by whom.
    ist = timezone(timedelta(hours=5, minutes=30))
    per_day = Counter(inbox.aware(a.at).astimezone(ist).date().isoformat() for a, _ in recent)
    today = inbox.now().astimezone(ist).date()
    groups_now = Counter(DISPOSITIONS[d["key"]][1] for d in now if d["key"] in DISPOSITIONS)
    return {
        "group_totals": {g: groups_now.get(g, 0) for g in ("positive", "follow_up", "negative", "other")},
        "by_day": [{"date": (today - timedelta(days=i)).isoformat(),
                    "count": per_day.get((today - timedelta(days=i)).isoformat(), 0)} for i in range(days - 1, -1, -1)],
        "by_person": [{"by": who_, "count": n} for who_, n in Counter(a.by for a, _ in recent).most_common()],
        "total": len(convs),
        "by_team": sum(d["source"] == "team" for d in now),
        "groups": [{"key": k, "label": v[0], "group": v[1], "count": by_key.get(k, 0)}
                   for k, v in DISPOSITIONS.items()],
        # The sheet's eleven categories (and Other), each with its sub-categories.
        "categories": [{"key": c.key, "label": c.label, "group": c.group, "icon": c.icon,
                        "count": sum(by_key.get(s.key, 0) for s in c.subs),
                        "subs": [{"key": s.key, "label": s.label, "count": by_key.get(s.key, 0), "action": s.action,
                                  "owner": s.owner} for s in c.subs]} for c in dz.CATEGORIES],
        # Documents uploaded, or marked Physical visit required: over to Eko Acquisition.
        "handed_over": sum(1 for c, d in zip(convs, now) if d["key"] == "int_visit"),
        "recent_days": days,
        "recent_count": len(recent),
        "recent_by_disposition": [{"key": k, "label": label(k), "count": n} for k, n in team_counts.most_common()],
        "recent": [{"phone": c.phone, "name": c.profile_name, "key": dz.normalise(a.value), "label": label(a.value), "note": a.note,
                    "by": a.by, "at": inbox.aware(a.at).isoformat()} for a, c in recent[:25]],
        "with_people": [{"phone": c.phone, "name": c.profile_name, "by": c.handled_by,
                         "since": inbox.aware(c.handled_since).isoformat() if c.handled_since else None}
                        for c in sorted(handled, key=lambda c: inbox.aware(c.handled_since) or inbox.now())],
    }


def leads(db: Session, key: str) -> dict:
    """
    The chats behind one count on the Dispositions tab (a category or one of
    its sub-categories), each with what the team needs to act: who they are,
    their business and place, the SBI branch nearest them and its AO, the
    campaign that reached them, and the next action item.
    """
    from src.models.inbox import FollowUp
    from src.services import applications, call_plan, lead_journey

    cat = dz.CATEGORY.get(key)
    sub = dz.SUBS.get(dz.normalise(key))
    if cat is None and sub is None:
        raise KeyError(key)
    keys = {s.key for s in cat.subs} if cat else {sub.key}

    convs = db.query(WhatsAppConversation).all()
    reach = reach_keys(db)
    rows = [(c, d) for c in convs for d in [current(c, reach)] if d["key"] in keys]
    phones = [c.phone for c, _ in rows]
    sources = applications._sources(db, phones)
    branches = applications._branches(db)
    now = inbox.now()
    pending: Dict[str, List[FollowUp]] = {}
    for f in (db.query(FollowUp).filter(FollowUp.phone.in_(phones), FollowUp.status.in_(("scheduled", "waiting")))
              .order_by(FollowUp.due_at).all() if phones else []):
        pending.setdefault(f.phone, []).append(f)
    window = call_plan.everyone_window(db) if phones else None

    out = []
    for c, d in rows:
        data = c.bot_data or {}
        coverage = data.get("coverage") or {}
        pin_info = coverage if coverage.get("pincode") else (data.get("typed_pin") or {})
        geo = pin_info.get("geo") or {}
        src = sources.get(c.phone) or {}
        branch = applications._nearest_branch(branches, pin_info.get("coords"))
        s = dz.SUBS.get(d["key"])
        # The next action item: one already planned, else the call the call plan proposes, else the sheet's action.
        nxt = None
        if c.documents_submitted_at or d["key"] == "int_visit":
            nxt = {"text": f"With {dz.HANDED_TO}: AutoGMap's part is done", "when": None, "owner": dz.HANDED_TO}
        elif pending.get(c.phone):
            f = pending[c.phone][0]
            it = lead_journey._item(f, now)
            nxt = {"text": it["text"], "when": inbox.aware(f.due_at).isoformat(), "owner": it["owner_label"]}
        else:
            plan = call_plan.for_lead(db, c, now, window)
            if plan["call"]:
                nxt = {"text": f"Call karein: {plan['goal']}", "when": plan["call_at"], "owner": lead_journey.owner_label("human")}
            elif s and s.action:
                nxt = {"text": s.action, "when": None, "owner": s.owner}
        out.append({
            "phone": c.phone,
            "name": c.profile_name,
            "disposition": d["label"],
            "disposition_key": d["key"],
            "since": d["at"],
            "by": d["by"],
            "business_name": src.get("business_name"),
            "category": src.get("category"),
            "pincode": pin_info.get("pincode"),
            "district": geo.get("district") or src.get("district"),
            "state": geo.get("state") or src.get("state"),
            "branch": branch,
            "campaign": src.get("campaign"),
            "language": call_plan.LANG.get(data.get("lang")),
            "stage": bot.STEP_LABELS.get(c.bot_step, c.bot_step) if c.bot_step else None,
            "documents_submitted": c.documents_submitted_at is not None,
            "next": nxt,
        })
    out.sort(key=lambda r: r["since"] or "", reverse=True)
    label_ = cat.label if cat else sub.label
    group = (cat or dz.CATEGORY[sub.category]).group
    return {"key": key, "label": label_, "group": group, "category": (cat or dz.CATEGORY[sub.category]).label,
            "action": sub.action if sub else None, "count": len(out), "leads": out}
