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

Everything a caller reads is in Hinglish, as the team speaks (the user,
2026-11-04); disposition names stay as the app shows them.
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
    "Fixed income ka vaada na karein: commission unke transactions par depend karta hai.",
    "₹3–5 lakh (location ke hisaab se) bolein, ek fixed amount nahi.",
    "Jo woh pehle bata chuke hain (neeche), woh dobara na poochhein.",
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
        return "1 ghante ke andar"
    if hours < 24:
        return f"{hours} ghante"
    days = round(hours / 24)
    return f"{days} din"


# --- What to talk about, by where they stopped ------------------------------------------------

def _stage_talk(step: Optional[str], data: dict, missing_docs: List[str]) -> dict:
    from src.services import onboarding_bot as bot

    invest = ("₹3–5 lakh, location ke hisaab se. Lagbhag ₹1–1.5 lakh ke devices Eko deta hai aur chalana bhi "
              "sikhata hai (laptop ya tab, biometric device, micro ATM, passbook printer, GPS dongle); thoda paisa "
              "unke apne e-wallet mein rehta hai jisse woh grahakon ka kaam karte hain; baaki mini branch set-up "
              "mein lagta hai. Har transaction par commission milta hai.")
    talk = {
        bot.CHOOSE_LANG: ("Interest check karein, aur kis bhasha mein baat karni hai",
                          ["Eko ke baare mein batayein: hum logon ko unki dukaan ya gaon mein SBI Customer Service Point (CSP), yaani SBI ki mini branch, kholne mein madad karte hain.",
                           "Poochhein kis bhasha mein baat karna aasaan hai, aur usi mein baat karein."]),
        bot.AWAIT_PIN: ("Unka PIN code lein, taaki paas ki SBI branch mile",
                        ["Jahan se CSP chalayenge, us jagah ka PIN code poochhein.",
                         "Wajah batayein: unke paas ki SBI branch hi unhe CSP degi."]),
        bot.AWAIT_EDUCATION: ("Padhai ke baare mein poochhein",
                              ["Kitna padhe hain, poochhein: kam se kam 12th pass zaroori hai.",
                               "Agar 12th se kam hai, to poochhein ki ghar mein koi 12th pass hai jo CSP chala sake."]),
        bot.AWAIT_FRANCHISE: ("Poochhein ki ₹3–5 lakh invest kar sakte hain ya nahi", ["Investment samjhayein: " + invest,
                                                                                      "Seedha poochhein: kya woh itna invest kar sakte hain?"]),
        bot.AWAIT_INVEST: ("Poochhein ki ₹3–5 lakh invest kar sakte hain ya nahi", ["Investment samjhayein: " + invest,
                                                                                   "Seedha poochhein: kya woh itna invest kar sakte hain?"]),
        bot.NOT_INVESTING: ("Kam investment wala option batayein",
                            ["Unhone kaha tha ki ₹3–5 lakh invest nahi kar sakte. Kam investment wale option ke baare mein batayein.",
                             "Poochhein kitna amount unke liye theek rahega."]),
        bot.ESAF_OFFERED: ("ESAF banking agent ka option batayein",
                           ["SBI ke ₹3–5 lakh nahi kar sakte: ESAF mein dukaan ka kiraya, stock ya bada investment nahi.",
                            "Sirf ₹1,999 registration; Micro ATM device chahiye to ₹1,300 + GST alag."]),
        bot.ESAF_DETAILS: ("ESAF ke liye aage badhne ko poochhein",
                           ["Services: AEPS, Micro ATM, money transfer, bill payment, recharge, account opening.",
                            "Poochhein kya ₹1,999 registration ke saath aage badhna hai."]),
        bot.ESAF_INTERESTED: ("ESAF registration poora karein",
                              ["₹1,999 registration ki payment aur Aadhaar, PAN, bank proof, dukaan par photo lein.",
                               "Aceware ka shop verification aur ₹100 stamp paper par agreement arrange karein."]),
        bot.AWAIT_DOCS: ("Documents upload karne ke liye taiyaar karein",
                         ["Documents ki list batayein: PAN, Aadhaar, passport size photo, aur upload page par baaki documents.",
                          "Poochhein abhi kaun se documents unke paas hain; Aadhaar DigiLocker se apne aap aa sakta hai."]),
        bot.AWAIT_UPLOAD: ("Documents upload karne mein madad karein",
                           (["Abhi baaki hain: " + ", ".join(missing_docs) + "."] if missing_docs else []) +
                           ["Call par bane rahein jab tak woh WhatsApp se upload link kholte hain.",
                            "Aadhaar card ki photo ke bina bhi DigiLocker se Aadhaar aa jata hai."]),
        bot.GUIDANCE_QA: ("Unke sawaalon ke jawab dein, aur shuruaat karwayein",
                          ["Unhone jo poochha hai (neeche), uska jawab dein.",
                           "Interested hain to chat mein Interested dabane ko kahein, ya call par hi details le lein."]),
    }
    goal, points = talk.get(step, ("Jaanein woh abhi kahan hain, aur agla step kya hai",
                                   ["Poochhein ki kya woh abhi bhi Eko ke saath SBI CSP kholne mein interested hain."]))
    return {"goal": goal, "points": points}


def _disposition_talk(key: Optional[str]) -> Optional[dict]:
    """A disposition that changes the call: trust, a callback, a hold, the decision maker."""
    key = dz.normalise(key)
    return {
        "int_trust": {"goal": "Unka shak door karein ki yeh asli hai ya nahi",
                      "points": ["Batayein Eko kaun hai: Eko India Financial Services, SBI ke saath milkar CSP set up karta hai.",
                                 "kiosk.eko.in dekhne ko kahein, aur hamara number dein jispar woh call kar sakein.",
                                 "Is call par documents ke liye zor na dein: pehle bharosa."]},
        "int_callback": {"goal": "Unke bataye time par call back karein", "points": ["Time dene ke liye shukriya kahein; chat jahan ruki thi wahin se baat shuru karein."]},
        "busy_busy": {"goal": "Call back: woh busy the", "points": ["Poochhein abhi baat karna theek hai; nahi to ek time fix karein."]},
        "busy_later": {"goal": "Call back: unhone baad mein call karne ko kaha tha", "points": ["Poochhein abhi baat karna theek hai; nahi to ek time fix karein."]},
        "busy_at_time": {"goal": "Unke bataye time par call back karein", "points": ["Chat jahan ruki thi wahin se baat shuru karein."]},
        "hold_later": {"goal": "Poochhein ki kya woh ab taiyaar hain", "points": ["Pehle unhone time maanga tha; poochhein kya ab kuch badla hai."]},
        "hold_financial": {"goal": "Poochhein ki kya ab invest kar sakte hain", "points": ["Paise ki dikkat thi; dobara poochhein, aur kam investment wala option bhi batayein."]},
        "hold_after_date": {"goal": "Poochhein ki kya woh ab taiyaar hain", "points": ["Unki batayi date aa gayi hai; poochhein kya aage badhein."]},
        "ndm_not_applicant": {"goal": "Jo apply karna chahte hain, unse baat karein", "points": ["Applicant ka number lein, ya unse baat karne ka time."]},
        "ndm_unavailable": {"goal": "Jo apply karna chahte hain, unse baat karein", "points": ["Poochhein applicant kab free honge."]},
        "lang_barrier": {"goal": "Unki bhasha mein baat karein", "points": ["Yeh call woh karein jo unki bhasha bolte hain."]},
        "int_docs_pending": {"goal": "Documents upload karne mein madad karein", "points": []},
    }.get(key)


def _outcomes(step: Optional[str]) -> dict:
    from src.services import onboarding_bot as bot
    yes = {bot.AWAIT_UPLOAD: "“Documents pending” (agar baad mein upload karenge), aur upload page check karein",
           bot.AWAIT_DOCS: "“Documents pending”: upload link chala jayega"}.get(step, "“More information required” ya “Documents pending”")
    return {"if_yes": yes,
            "if_no": "“Not interested currently”, ya paise ki wajah ho to “Investment issue”",
            "no_answer": "“No answer” (RNR): bot kal phir try karega",
            "later": "“Asked to call later”, ya unke bataye time ke saath “Call at specific time”"}


def _known(conv: WhatsAppConversation) -> List[str]:
    data = conv.bot_data or {}
    out = []
    cov = data.get("coverage") or {}
    place = ", ".join(x for x in (cov.get("district"), cov.get("state")) if x)
    if cov.get("pincode"):
        out.append(f"PIN {cov['pincode']}" + (f" ({place})" if place else "")
                   + ("" if cov.get("served", True) else ": paas mein hamari SBI branch nahi hai"))
    edu = {"12": "12th pass", "grad": "Graduate", "other": "12th se kam"}.get(data.get("education"))
    if edu:
        out.append(f"Padhai: {edu}")
    if data.get("can_invest") is True:
        out.append("₹3–5 lakh invest kar sakte hain")
    elif data.get("can_invest") is False:
        out.append("Kaha tha ₹3–5 lakh invest nahi kar sakte")
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
    return [d["label"] for d in bot.required_for(conv) if d["key"] not in done]


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
        return none(f"Documents aa gaye hain: lead ab {dz.HANDED_TO} ke paas hai.")
    if opt_out.blocks_followups(opt_out.entry(db, conv.phone)):
        return none("Unhone contact na karne ko kaha hai.")
    if sub and sub.closes:
        return none(f"Lead “{sub.label}” ke saath band ho chuki hai.")

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
        when_why = [f"Unhone isi time call back karne ko kaha tha ({dz.label(timed.disposition)})."]
        after = None
    else:
        if last_ours is None or (last_in is not None and inbox.aware(last_in.created_at) > inbox.aware(last_ours.created_at)):
            return none("Unhone hamare last message ka jawab de diya hai: pehle bot ya team jawab degi.")
        sent = inbox.aware(last_ours.created_at)
        if (conv.disposition_at and conv.disposition_by and conv.disposition_by != "bot"
                and inbox.aware(conv.disposition_at) > sent):
            return none(f"Hamare last message ke baad {conv.disposition_by.split('@')[0]} ne “{dz.label(conv.disposition)}” record kiya hai.")
        status = (last_ours.status or "SENT").upper()
        wait, seen = {"READ": (READ_WAIT, "Unhone hamara last message padh liya par jawab nahi diya"),
                      "FAILED": (FAILED_WAIT, "WhatsApp hamara last message deliver nahi kar paya: ab sirf call se hi baat ho sakti hai"),
                      "DELIVERED": (DELIVERED_WAIT, "Hamara last message pahunch gaya par abhi padha nahi gaya")}.get(
            status, (DELIVERED_WAIT, "Hamara last message chala gaya; WhatsApp ne abhi padhne ki khabar nahi di"))
        when_why = [f"{seen}; uske {_wait_text(wait)} baad call karein, taaki pehle woh WhatsApp par jawab de sakein."]
        own = [inbox.aware(m.created_at).astimezone(IST).hour for m in messages if m.direction == "IN"]
        start = _window_of(own) if len(own) >= OWN_REPLIES_MIN else None
        if start is not None:
            when_why.append(f"Yeh aksar {_hour_label(start)} se {_hour_label(start + WINDOW)} ke beech message karte hain.")
        else:
            start = fallback_window if fallback_window is not None else everyone_window(db)
            when_why.append(f"Inke apne messages kam hain; hamari campaigns se jude log zyaadatar "
                            f"{_hour_label(start)} se {_hour_label(start + WINDOW)} ke beech jawab dete hain.")
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
        "opening": (f"Namaste {conv.profile_name or ''} ji, main Eko se baat kar raha/rahi hoon. Aapne WhatsApp par SBI CSP "
                    "mein interest dikhaya tha, usi ke baare mein call kiya hai.").replace("Namaste  ji", "Namaste ji"),
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
