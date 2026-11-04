"""
When to call a lead, and what to talk about: one call plan per lead, for the
team today and for the AI calling agent once it is connected (Sumit's agent,
through its MCP: the plan is plain data it can be handed as it is).

WHEN. A call follows the bot's last message that the lead has not answered
(its question, or a nudge). How long to wait depends on what WhatsApp says
happened to that message:
- read and not answered: they saw it, so a call soon helps (READ_WAIT);
- delivered, not read yet: give them longer to see it (DELIVERED_WAIT);
- not delivered: WhatsApp cannot reach them, so only a call can (FAILED_WAIT).
The time is then moved into the hours this lead writes back in (from their
own messages), or, with too few of those, the hours everyone our campaigns
reached writes back in; never outside CALL_HOURS. A time the lead asked for
(a callback, a follow-up date) is kept exactly. No call is planned once they
have answered, handed over, closed, asked not to be contacted, or a person
recorded a disposition after that message (the call was made).

WHAT. The goal of the call from where they stopped, what we already know
(so it is not asked again), the questions they asked us, the points to make,
what to avoid, and what to record as the outcome either way.
"""
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.inbox import ChatActivity, FollowUp, OnboardingDocument, WhatsAppConversation, WhatsAppMessage
from src.services import dispositions as dz, inbox

IST = timezone(timedelta(hours=5, minutes=30))
READ_WAIT = timedelta(hours=2)
DELIVERED_WAIT = timedelta(hours=4)
FAILED_WAIT = timedelta(hours=1)
CALL_HOURS = (9, 20)
WINDOW = 2
# Their own replies say when they are free only once there are a few.
OWN_REPLIES_MIN = 3
TIMED_PURPOSES = ("callback_due", "checking_in")

LANG = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish", "gu": "Gujarati", "pa": "Punjabi", "mr": "Marathi",
        "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam", "or": "Odia"}

AVOID = [
    "Do not promise a fixed income: the commission depends on the transactions they do.",
    "Say ₹3–5 lakh depending on the location, not one figure.",
    "Do not ask again what they have already told us (below).",
]


def _hour_label(h: int) -> str:
    return f"{((h + 11) % 12) + 1} {'AM' if h < 12 else 'PM'}"


def _window_of(hours: List[int]) -> Optional[int]:
    """The start of the two hours inside CALL_HOURS with the most replies."""
    counts = Counter(h for h in hours if CALL_HOURS[0] <= h < CALL_HOURS[1])
    if not counts:
        return None
    starts = range(CALL_HOURS[0], CALL_HOURS[1] - WINDOW + 1)
    return max(starts, key=lambda s: (sum(counts[s + i] for i in range(WINDOW)), -s))


def everyone_window(db: Session) -> int:
    """When the people our campaigns reached write back most: the fallback for a lead with few replies."""
    from src.services import growth_plan
    return growth_plan._call_window(db, growth_plan._people(db))["from_hour"]


def _into_window(at: datetime, start_hour: int) -> datetime:
    """The first moment at or after `at` inside [start_hour, start_hour + WINDOW) IST."""
    local = at.astimezone(IST)
    begin = datetime.combine(local.date(), time(start_hour), tzinfo=IST)
    end = begin + timedelta(hours=WINDOW)
    if local < begin:
        return begin.astimezone(timezone.utc)
    if local < end:
        return at
    return (begin + timedelta(days=1)).astimezone(timezone.utc)


def _wait_text(d: timedelta) -> str:
    hours = round(d.total_seconds() / 3600)
    if hours < 1:
        return "within the hour"
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = round(hours / 24)
    return f"{days} day{'s' if days != 1 else ''}"


# --- What to talk about, by where they stopped ------------------------------------------------

def _stage_talk(step: Optional[str], data: dict, missing_docs: List[str]) -> dict:
    from src.services import onboarding_bot as bot

    invest = ("₹3–5 lakh, depending on the location. About ₹1–1.5 lakh is the devices Eko gives and trains them on "
              "(laptop or tab, biometric device, micro ATM, passbook printer, GPS dongle); some stays with them in "
              "their own e-wallet to serve customers; the rest sets up the mini branch. They earn a commission on "
              "every transaction.")
    talk = {
        bot.CHOOSE_LANG: ("See whether they are interested, and in which language to talk",
                          ["Introduce Eko: we help people open an SBI Customer Service Point (CSP), a mini SBI branch, in their shop or village.",
                           "Ask which language they are comfortable in, and continue in it."]),
        bot.AWAIT_PIN: ("Get their PIN code, to find their nearest SBI branch",
                        ["Ask for the PIN code of the place they would run the CSP from.",
                         "Say why: the SBI branch near them has to take them on."]),
        bot.AWAIT_EDUCATION: ("Find out how far they have studied",
                              ["Ask their education: 12th pass or more is needed.",
                               "If they are below 12th, ask whether someone in the family who has passed 12th could run it."]),
        bot.AWAIT_FRANCHISE: ("Find out whether they can invest ₹3–5 lakh", ["Explain the investment: " + invest,
                                                                             "Ask plainly whether they can invest it."]),
        bot.AWAIT_INVEST: ("Find out whether they can invest ₹3–5 lakh", ["Explain the investment: " + invest,
                                                                          "Ask plainly whether they can invest it."]),
        bot.NOT_INVESTING: ("Offer the lower-investment option",
                            ["They said they cannot invest ₹3–5 lakh. Tell them about the lower-investment option.",
                             "Ask what amount would work for them."]),
        bot.AWAIT_DOCS: ("Get them ready to upload their documents",
                         ["Go through the documents: PAN, Aadhaar, a passport size photo, and the others on the upload page.",
                          "Ask which they have now; DigiLocker can fill Aadhaar for them."]),
        bot.AWAIT_UPLOAD: ("Help them upload their documents",
                           (["Still missing: " + ", ".join(missing_docs) + "."] if missing_docs else []) +
                           ["Offer to stay on the line while they open the upload link from WhatsApp.",
                            "DigiLocker can fill Aadhaar without a photo of the card."]),
        bot.GUIDANCE_QA: ("Answer their questions, and get them started",
                          ["Answer what they asked (below).",
                           "If they are interested, ask them to tap Interested in the chat, or take the details on the call."]),
    }
    goal, points = talk.get(step, ("Find out where they stand, and the next step",
                                   ["Ask whether they are still interested in opening an SBI CSP with Eko."]))
    return {"goal": goal, "points": points}


def _disposition_talk(key: Optional[str]) -> Optional[dict]:
    """A disposition that changes the call: trust, a callback, a hold, the decision maker."""
    key = dz.normalise(key)
    return {
        "int_trust": {"goal": "Answer their doubt about whether this is genuine",
                      "points": ["Say who Eko is: Eko India Financial Services works with SBI to set up CSPs.",
                                 "Point them to kiosk.eko.in, and offer our number to call back on.",
                                 "Do not push for documents on this call: trust first."]},
        "int_callback": {"goal": "Call back at the time they asked", "points": ["Thank them for their time; pick up where the chat stopped."]},
        "busy_busy": {"goal": "Call back: they were busy", "points": ["Ask if now is a good time; if not, fix a time."]},
        "busy_later": {"goal": "Call back: they asked us to call later", "points": ["Ask if now is a good time; if not, fix a time."]},
        "busy_at_time": {"goal": "Call back at the time they asked", "points": ["Pick up where the chat stopped."]},
        "hold_later": {"goal": "Check whether they are ready now", "points": ["They asked for time earlier; ask whether things have changed."]},
        "hold_financial": {"goal": "Check whether they can invest now", "points": ["Money was the problem; ask again, and mention the lower-investment option."]},
        "hold_after_date": {"goal": "Check whether they are ready now", "points": ["The date they gave has come; ask whether to go ahead."]},
        "ndm_not_applicant": {"goal": "Reach the person who wants to apply", "points": ["Ask for the applicant's number, or a time to speak to them."]},
        "ndm_unavailable": {"goal": "Reach the person who wants to apply", "points": ["Ask when the applicant is free."]},
        "lang_barrier": {"goal": "Talk in their language", "points": ["Have someone who speaks their language make this call."]},
        "int_docs_pending": {"goal": "Help them upload their documents", "points": []},
    }.get(key)


def _outcomes(step: Optional[str]) -> dict:
    from src.services import onboarding_bot as bot
    yes = {bot.AWAIT_UPLOAD: "Documents pending (if they will upload later), and check the upload page",
           bot.AWAIT_DOCS: "Documents pending: the upload link goes out"}.get(step, "More information required, or Documents pending")
    return {"if_yes": yes,
            "if_no": "Not interested currently, or Investment issue if money is the reason",
            "no_answer": "No answer (RNR): the bot tries again tomorrow",
            "later": "Asked to call later, or Call at specific time with the time they give"}


def _known(conv: WhatsAppConversation) -> List[str]:
    data = conv.bot_data or {}
    out = []
    cov = data.get("coverage") or {}
    place = ", ".join(x for x in (cov.get("district"), cov.get("state")) if x)
    if cov.get("pincode"):
        out.append(f"PIN {cov['pincode']}" + (f" ({place})" if place else "")
                   + ("" if cov.get("served", True) else ": no SBI branch of ours nearby"))
    edu = {"12": "12th pass", "grad": "Graduate", "other": "Below 12th"}.get(data.get("education"))
    if edu:
        out.append(f"Education: {edu}")
    if data.get("can_invest") is True:
        out.append("Can invest ₹3–5 lakh")
    elif data.get("can_invest") is False:
        out.append("Said they cannot invest ₹3–5 lakh")
    return out


def _their_questions(db: Session, conv: WhatsAppConversation, messages: List[WhatsAppMessage]) -> List[str]:
    from src.services import tickets
    out = []
    t = tickets.open_ticket(db, conv.phone)
    if t and (t.latest_question or t.question):
        out.append((t.latest_question or t.question).strip()[:200])
    for m in reversed(messages):
        if len(out) >= 3:
            break
        body = (m.body or "").strip()
        if m.direction == "IN" and m.kind == "text" and len(body) > 12 and "?" in body and body[:200] not in out:
            out.append(body[:200])
    return out


def _missing_docs(db: Session, conv: WhatsAppConversation) -> List[str]:
    from src.services import onboarding_bot as bot
    keys = [k for (k,) in db.query(OnboardingDocument.doc_type).filter(OnboardingDocument.phone == conv.phone)]
    done = bot.rows_done(keys)
    return [d["label"] for d in bot.DOCUMENTS if d["required"] and d["key"] not in done]


# --- The plan -------------------------------------------------------------------------------------

def for_lead(db: Session, conv: WhatsAppConversation, now: Optional[datetime] = None,
             fallback_window: Optional[int] = None) -> dict:
    """This lead's call plan: whether a call is due, when, why, and what to talk about."""
    from src.services import opt_out

    now = now or inbox.now()
    name = conv.profile_name or conv.phone
    base = {"phone": conv.phone, "name": name}
    sub = dz.sub(conv.disposition)

    def none(why: str) -> dict:
        return {**base, "call": False, "why": why}

    if conv.documents_submitted_at:
        return none(f"Documents are in: the lead is with {dz.HANDED_TO}.")
    if opt_out.blocks_followups(opt_out.entry(db, conv.phone)):
        return none("They asked not to be contacted.")
    if sub and sub.closes:
        return none(f"Closed as “{sub.label}”.")

    messages = (db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == conv.phone)
                .order_by(WhatsAppMessage.created_at).all())
    last_in = next((m for m in reversed(messages) if m.direction == "IN"), None)
    last_ours = next((m for m in reversed(messages) if m.direction == "OUT"), None)

    # A time they asked for comes first, kept as it is.
    timed = (db.query(FollowUp).filter(FollowUp.phone == conv.phone, FollowUp.status.in_(("scheduled", "waiting")),
                                       FollowUp.purpose.in_(TIMED_PURPOSES))
             .order_by(FollowUp.due_at).first())
    if timed is not None:
        call_at = inbox.aware(timed.due_at)
        when_why = [f"They asked to be called back then ({dz.label(timed.disposition)})."]
        after = None
    else:
        if last_ours is None or (last_in is not None and inbox.aware(last_in.created_at) > inbox.aware(last_ours.created_at)):
            return none("They answered our last message: the bot or the team replies first.")
        sent = inbox.aware(last_ours.created_at)
        if (conv.disposition_at and conv.disposition_by and conv.disposition_by != "bot"
                and inbox.aware(conv.disposition_at) > sent):
            return none(f"{conv.disposition_by.split('@')[0]} recorded “{dz.label(conv.disposition)}” after our last message.")
        status = (last_ours.status or "SENT").upper()
        wait, seen = {"READ": (READ_WAIT, "They read our last message and did not answer"),
                      "FAILED": (FAILED_WAIT, "WhatsApp could not deliver our last message: only a call can reach them"),
                      "DELIVERED": (DELIVERED_WAIT, "Our last message reached them but is not read yet")}.get(
            status, (DELIVERED_WAIT, "Our last message has gone; WhatsApp has not said it was read"))
        when_why = [f"{seen}; wait {_wait_text(wait)} after it, so they can answer on WhatsApp first."]
        own = [inbox.aware(m.created_at).astimezone(IST).hour for m in messages if m.direction == "IN"]
        start = _window_of(own) if len(own) >= OWN_REPLIES_MIN else None
        if start is not None:
            when_why.append(f"They usually write between {_hour_label(start)} and {_hour_label(start + WINDOW)}.")
        else:
            start = fallback_window if fallback_window is not None else everyone_window(db)
            when_why.append(f"Too few replies of their own to tell; people our campaigns reached write back most "
                            f"between {_hour_label(start)} and {_hour_label(start + WINDOW)}.")
        call_at = _into_window(sent + wait, start)
        after = call_at - sent

    talk = _disposition_talk(conv.disposition) if conv.disposition else None
    stage = _stage_talk(conv.bot_step, conv.bot_data or {}, _missing_docs(db, conv) if conv.bot_step else [])
    goal = (talk or {}).get("goal") or stage["goal"]
    points = ((talk or {}).get("points") or []) + stage["points"]
    lang = LANG.get((conv.bot_data or {}).get("lang"), "Hindi")
    return {
        **base,
        "call": True,
        "call_at": call_at.isoformat(),
        "after_message": _wait_text(after) if after is not None else None,
        "overdue": call_at <= now,
        "why": when_why,
        "language": lang,
        "disposition": dz.label(conv.disposition),
        "goal": goal,
        "opening": f"Namaste {conv.profile_name or ''}, this is Eko, about the SBI CSP you showed interest in on WhatsApp."
                   .replace("Namaste ,", "Namaste,"),
        "points": points,
        "known": _known(conv),
        "their_questions": _their_questions(db, conv, messages),
        "avoid": AVOID,
        "record": _outcomes(conv.bot_step),
    }


def due(db: Session, now: Optional[datetime] = None) -> List[dict]:
    """Every lead a call is planned for, soonest first: for the action items queue and the calling agent."""
    from src.services import growth_plan, tickets

    now = now or inbox.now()
    tests = tickets._test_phones(db)
    window = everyone_window(db)
    people = [c for c in growth_plan._people(db) if c.phone not in tests and c.bot_step]
    plans = [p for p in (for_lead(db, c, now, window) for c in people) if p["call"]]
    return sorted(plans, key=lambda p: p["call_at"])
