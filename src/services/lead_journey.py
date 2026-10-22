"""
Every lead's journey, step by step, with dates: when they became interested
and what we did next, when they moved on and what we did then, up to their
documents and the hand-over to Eko Acquisition ("Physical visit required:
assign to DC, schedule visit, DC will give report to Eko"). The same for the
other ways a journey goes: not interested, not eligible, outside our area,
cannot invest, a question for the team, gone quiet (the user, 2026-10-21).

Nothing new is stored for it; it is read from what is already kept, so
leads from before today have their journey too:
- the bot's own replies mark each step: when it asks for the PIN code, the
  person has just chosen their language; when it asks about education, the
  PIN was one we serve; and so on. The person's step is dated by their
  message just before, our action by the bot's reply;
- the campaign message that reached them;
- what the team did (took over, recorded an outcome), the nudges the
  dispositions sent and how they went, and the tickets raised and solved.

A step is {kind, key, at, what, action, action_at, by, tone}: "what" is what
the lead did or what happened, "action" what we did about it.
"""
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.inbox import AttentionTicket, ChatActivity, FollowUp, WhatsAppConversation, WhatsAppMessage
from src.services import bot_messages, dispositions as dz, inbox

# The stages of AutoGMap's part, in order; the progress bar is how far along them a lead got.
FUNNEL = ["campaign", "interested", "language", "pin", "education", "investment", "docs_ready", "uploaded",
          "handed_over"]
FUNNEL_LABELS = {
    "campaign": "Campaign reached", "interested": "Interested", "language": "Language", "pin": "PIN code",
    "education": "Education", "investment": "Investment", "docs_ready": "Documents ready",
    "uploaded": "Documents uploaded", "handed_over": "Handed to Eko Acquisition",
}

# A bot message, by the text it was written from: (stage reached, what the lead did, our action, tone).
STEP_OF: Dict[str, tuple] = {
    "language_prompt": ("interested", "Became interested", "Asked which language they prefer", "positive"),
    "greeting": ("wrote_in", "Wrote to us", "Greeted them and offered Interested or Personal guidance", "neutral"),
    "guidance_open": ("guidance", "Asked for personal guidance", "Invited their questions", "positive"),
    "ask_pin": ("language", "Chose their language", "Asked for their PIN code", "positive"),
    "ask_education": ("pin", "Shared a PIN code we serve", "Asked about their education", "positive"),
    "invest_explained": ("education", "Met the education requirement",
                         "Explained the ₹5 lakh investment and asked whether they can invest", "positive"),
    "ask_franchise": ("education", "Met the education requirement", "Asked about running it as a franchise", "positive"),
    "ask_docs": ("investment", "Can invest", "Asked whether their documents are ready", "positive"),
    "send_link": ("docs_ready", "Has the documents ready", "Sent the document upload link", "positive"),
    "docs_later": ("docs_later", "Will arrange the documents later", "Noted it; the bot reminds them", "neutral"),
    "thanks": ("uploaded", "Uploaded their documents", "Thanked them", "positive"),
    "not_served": ("not_served", "PIN code is outside our area", "Told them Eko does not serve there yet", "negative"),
    "not_eligible": ("not_eligible", "Did not meet the education requirement", "Told them politely", "negative"),
    "not_investing": ("not_investing", "Cannot invest right now", "Explained the investment and noted it", "negative"),
}
# Bot messages that are events rather than steps: (what happened, our action).
EVENT_OF: Dict[str, tuple] = {
    "nudge": ("Went quiet for an hour", "Sent a reminder with the same question"),
    "resume": (None, "The bot carried on where they left off"),
    "question_ack": ("Asked something the bot could not answer", "Passed to the team; a ticket was raised"),
    "handover": ("Asked for a person", "Passed the chat to the team"),
    "bad_pin": ("Sent a PIN code we could not read", "Asked for the PIN code again"),
    "unknown_pin": ("Sent a PIN code we could not find", "Asked for the PIN code again"),
    "remind_upload": (None, "Reminded them to upload their documents"),
    "already_submitted": ("Wrote again after uploading", "Told them their documents are already with us"),
    "not_served_again": ("Wrote again from outside our area", "Reminded them Eko does not serve there yet"),
    "guidance_more": ("Asked a question", "Answered it"),
}
# Checked first: these open a message that goes on with a question.
_LEADING = ("nudge", "resume")
_ORDER = list(_LEADING) + list(EVENT_OF) + list(STEP_OF)
_ORDER = list(dict.fromkeys(_ORDER))


def _prefixes() -> Dict[str, List[str]]:
    """The fixed opening of each message, in every language, to recognise it by."""
    out: Dict[str, List[str]] = defaultdict(list)
    sources = list(bot_messages.MESSAGES.values()) + [bot_messages.HINGLISH]
    for key in _ORDER:
        for msgs in sources:
            text = msgs.get(key)
            if not isinstance(text, str):
                continue
            head = text.split("{", 1)[0].strip()
            # The first line is enough, and stays the same whatever is filled in below it.
            head = head.split("\n", 1)[0].strip()[:60]
            if len(head) >= 12 and head not in out[key]:
                out[key].append(head)
    return out


# The cannot-invest reply before it offered the lower-investment option (22 Oct 2026),
# so older chats still read as "Cannot invest right now".
_OLDER = {"not_investing": [
    "Thank you for letting us know. If anything changes, just reply here and our team will be happy to help.",
    "बताने के लिए धन्यवाद। अगर आगे कुछ बदलता है, तो यहाँ जवाब दें, हमारी टीम आपकी मदद करेगी।",
    "ਦੱਸਣ ਲਈ ਧੰਨਵਾਦ। ਜੇ ਅੱਗੇ ਕੁਝ ਬਦਲਦਾ ਹੈ, ਤਾਂ ਇੱਥੇ ਜਵਾਬ ਦਿਓ, ਸਾਡੀ ਟੀਮ ਤੁਹਾਡੀ ਮਦਦ ਕਰੇਗੀ।",
    "જણાવવા બદલ આભાર. જો આગળ કંઈ બદલાય, તો અહીં જવાબ આપો, અમારી ટીમ તમને મદદ કરશે.",
    "कळवल्याबद्दल धन्यवाद. पुढे काही बदलल्यास इथे उत्तर द्या, आमची टीम तुम्हाला मदत करेल.",
    "জানানোর জন্য ধন্যবাদ। পরে কিছু বদলালে এখানে উত্তর দিন, আমাদের টিম আপনাকে সাহায্য করবে।",
    "தெரிவித்ததற்கு நன்றி. பின்னர் ஏதாவது மாறினால் இங்கே பதில் அனுப்புங்கள், எங்கள் குழு உங்களுக்கு உதவும்.",
    "తెలియజేసినందుకు ధన్యవాదాలు. తర్వాత ఏదైనా మారితే ఇక్కడ జవాబు ఇవ్వండి, మా బృందం మీకు సహాయం చేస్తుంది.",
    "ತಿಳಿಸಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ಮುಂದೆ ಏನಾದರೂ ಬದಲಾದರೆ ಇಲ್ಲಿ ಉತ್ತರಿಸಿ, ನಮ್ಮ ತಂಡ ನಿಮಗೆ ಸಹಾಯ ಮಾಡುತ್ತದೆ.",
    "അറിയിച്ചതിന് നന്ദി. പിന്നീട് എന്തെങ്കിലും മാറിയാൽ ഇവിടെ മറുപടി നൽകുക, ഞങ്ങളുടെ ടീം സഹായിക്കും.",
    "ଜଣାଇଥିବାରୁ ଧନ୍ୟବାଦ। ପରେ କିଛି ବଦଳିଲେ ଏଠାରେ ଉତ୍ତର ଦିଅନ୍ତୁ, ଆମ ଟିମ୍ ଆପଣଙ୍କୁ ସାହାଯ୍ୟ କରିବ।",
    "Batane ke liye dhanyavaad. Agar aage kuch badalta hai, to yahan jawab dein, hamari team aapki madad karegi."
]}

_PREFIXES = _prefixes()
for _key, _texts in _OLDER.items():
    _PREFIXES[_key] += [t.split("\n", 1)[0].strip()[:60] for t in _texts]


def classify(body: Optional[str]) -> Optional[str]:
    """Which bot message this is, by the text it was written from; None for anything else (an FAQ answer)."""
    if not body:
        return None
    for key in _LEADING:
        if any(body.startswith(p) for p in _PREFIXES.get(key, [])):
            # A reminder or a resume: what follows it is the question asked again.
            return key
    for key in _ORDER:
        if key in _LEADING:
            continue
        if any(p in body for p in _PREFIXES.get(key, [])):
            return key
    return None


def _who(email: Optional[str]) -> str:
    from src.services.handover import who
    return who(email)


def _iso(dt) -> Optional[str]:
    dt = inbox.aware(dt)
    return dt.isoformat() if dt else None


def _said(m: WhatsAppMessage) -> str:
    if m.kind == "text":
        return (m.body or "").strip()
    if m.kind in ("button", "interactive"):
        p = m.payload or {}
        return (p.get("title") or p.get("text") or m.body or "").strip()
    if m.kind == "audio":
        return ((m.payload or {}).get("transcript") or "a voice note").strip()
    return m.kind


_PURPOSE_WORDS = {
    "more_info": "invited their questions", "callback_confirm": "confirmed we will get back at their time",
    "callback_due": "got back at the time they asked", "docs_reminder": "reminded them to upload documents",
    "lower_investment": "offered the lower-investment option",
    "missed_you": "tried them again", "decision_maker": "asked for the applicant's contact",
    "checking_in": "checked back on the follow-up date", "choose_language": "asked which language they prefer",
}
_LANG = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish", "gu": "Gujarati", "pa": "Punjabi", "mr": "Marathi",
         "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam", "or": "Odia"}


def build(db: Session, conv: WhatsAppConversation, *, messages: Optional[List[WhatsAppMessage]] = None,
          activities: Optional[List[ChatActivity]] = None, followups: Optional[List[FollowUp]] = None,
          tickets: Optional[List[AttentionTicket]] = None, sent_at: Optional[datetime] = None) -> dict:
    """The journey of one lead: its steps in order, how far it got, and how it stands."""
    phone = conv.phone
    if messages is None:
        messages = (db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == phone)
                    .order_by(WhatsAppMessage.created_at).all())
    if activities is None:
        activities = db.query(ChatActivity).filter(ChatActivity.phone == phone).all()
    if followups is None:
        followups = db.query(FollowUp).filter(FollowUp.phone == phone).all()
    if tickets is None:
        tickets = db.query(AttentionTicket).filter(AttentionTicket.phone == phone).all()
    if sent_at is None:
        from src.models.whatsapp import WhatsAppCampaignRecipient
        row = (db.query(WhatsAppCampaignRecipient).filter(WhatsAppCampaignRecipient.phone == phone,
                                                          WhatsAppCampaignRecipient.sent_at.isnot(None))
               .order_by(WhatsAppCampaignRecipient.sent_at).first())
        sent_at = row.sent_at if row else None

    steps: List[dict] = []
    reached: Dict[str, str] = {}

    def add(kind, key, at, what, action=None, action_at=None, by="bot", tone="neutral", detail=None):
        steps.append({"kind": kind, "key": key, "at": _iso(at), "what": what, "action": action,
                      "action_at": _iso(action_at), "by": by, "tone": tone, "detail": detail})
        if kind == "stage" and key not in reached:
            reached[key] = _iso(at)

    if sent_at:
        add("stage", "campaign", sent_at, "Our campaign message reached them",
            "Waiting for them to tap a button", sent_at, tone="neutral")

    last_in: Optional[WhatsAppMessage] = None
    answered_since_in = False
    for m in sorted(messages, key=lambda x: inbox.aware(x.created_at)):
        if m.direction == "IN":
            last_in, answered_since_in = m, False
            continue
        if m.sent_by != "bot":
            if m.sent_by and m.sent_by not in ("campaign",):
                add("event", "team_reply", last_in.created_at if last_in else m.created_at,
                    f"Wrote: “{_said(last_in)[:120]}”" if last_in and not answered_since_in else None,
                    f"{_who(m.sent_by)} replied: “{(m.body or '').strip()[:120]}”", m.created_at, by=m.sent_by)
                answered_since_in = True
            continue
        key = classify(m.body)
        lead_at = last_in.created_at if last_in and not answered_since_in else m.created_at
        if key in STEP_OF:
            stage, what, action, tone = STEP_OF[key]
            if key == "ask_pin" and "interested" not in reached:
                stage, what = "interested", "Became interested"
            if stage == "uploaded" and conv.documents_submitted_at:
                lead_at = conv.documents_submitted_at
            if stage in reached and stage in FUNNEL:
                # The same question asked again later: an event, not a new step.
                add("event", f"again:{stage}", lead_at, None, f"{action} (again)", m.created_at)
            else:
                add("stage", stage, lead_at, what, action, m.created_at, tone=tone)
        elif key in EVENT_OF:
            what, action = EVENT_OF[key]
            add("event", key, lead_at if what else m.created_at, what, action, m.created_at,
                tone="warning" if key in ("question_ack", "handover") else "neutral")
        else:
            # A reply that is none of the bot's set messages: an answer from Eko's FAQ, or an
            # older wording. Said as it was, rather than guessed at.
            from src.services.onboarding_bot import looks_like_question
            reply = " ".join((m.body or "").split())
            reply = f"The bot replied: “{reply[:110]}{'…' if len(reply) > 110 else ''}”"
            if last_in is not None and not answered_since_in:
                said = _said(last_in)
                what = f"Asked: “{said[:120]}”" if looks_like_question(said) else f"Wrote: “{said[:120]}”"
                add("event", "answered", last_in.created_at, what, reply, m.created_at)
            else:
                add("event", "bot_said", m.created_at, None, reply, m.created_at)
        answered_since_in = True

    for a in activities:
        if a.kind == "disposition":
            s = dz.sub(a.value)
            tone = {"positive": "positive", "negative": "negative"}.get(dz.group(a.value), "neutral")
            add("stage", f"disposition:{dz.normalise(a.value)}", a.at, f"Outcome recorded: {dz.label(a.value) or a.value}",
                "; ".join(dz.plan_text(s, calls=False)) if s and dz.plan_text(s) else "Noted; nothing more to send", a.at,
                by=a.by, tone=tone, detail=a.note)
        elif a.kind == "to_person":
            add("event", "to_person", a.at, None, f"{_who(a.by)} took the chat over from the bot", a.at, by=a.by)
        elif a.kind == "to_bot":
            add("event", "to_bot", a.at, None, f"{_who(a.by)} handed the chat back to the bot", a.at, by=a.by)

    for f in followups:
        if f.wants == dz.TASK:
            if f.status == "cancelled":
                continue
            owner = {"human": "the team", "dc": "the District Coordinator"}.get(f.owner, f.owner)
            add("event", "task", f.created_at, None, f"Task for {owner}: {f.task}"
                + (f" — done by {_who(f.done_by)}" if f.status == "done" and f.done_by else ""), f.done_at or f.created_at,
                by=f.done_by or f.created_by)
            continue
        if f.wants == dz.API:
            if f.status == "sent":
                add("event", "to_acquisition", f.sent_at, None, f"Sent to {dz.HANDED_TO} through their API", f.sent_at,
                    tone="handover")
            elif f.status in ("scheduled", "waiting", "failed"):
                add("event", "to_acquisition", f.created_at, None,
                    f"Waiting to send to {dz.HANDED_TO}" if f.status != "failed" else f"Could not send to {dz.HANDED_TO}",
                    f.created_at, tone="planned" if f.status != "failed" else "negative", detail=f.note)
            continue
        if f.status in ("scheduled", "waiting"):
            add("event", "planned", f.due_at, None,
                f"Next: a WhatsApp message to {dz.PURPOSE_PLAIN.get(f.purpose, f.purpose.replace('_', ' '))}"
                + (" (waiting for Meta to approve it)" if f.status == "waiting" else ""), f.due_at, tone="planned")
            continue
        if f.status == "cancelled":
            continue
        lang = f" in {_LANG.get(f.language, f.language)}" if f.language else ""
        outcome = {"replied": "They replied", "no_answer": "No reply in a day: recorded as RNR",
                   "failed": "Could not be delivered: recorded as Unreachable"}.get(f.status)
        add("event", "nudge", f.sent_at or f.due_at, None,
            f"WhatsApp nudge{lang}: we {_PURPOSE_WORDS.get(f.purpose, f.purpose)}", f.sent_at or f.due_at,
            tone="negative" if f.status == "failed" else "neutral", detail=outcome)

    for t in tickets:
        if t.resolved_at:
            by = "the bot" if t.resolved_by == "bot" else _who(t.resolved_by)
            add("event", "ticket_solved", t.resolved_at, None, f"Question solved by {by}", t.resolved_at,
                by=t.resolved_by or "team")

    # The end of AutoGMap's part: documents in, over to Eko Acquisition.
    visit = dz.SUBS["int_visit"]
    handed_at = conv.documents_submitted_at or next(
        (a.at for a in activities if a.kind == "disposition" and dz.normalise(a.value) == "int_visit"), None)
    if handed_at:
        if "uploaded" not in reached and conv.documents_submitted_at:
            add("stage", "uploaded", conv.documents_submitted_at, "Uploaded their documents", None, None, tone="positive")
        add("stage", "handed_over", handed_at, f"{visit.label}: handed to {dz.HANDED_TO}",
            f"{visit.action} (by {dz.HANDED_TO})", handed_at, by=dz.HANDED_TO, tone="handover")

    steps.sort(key=lambda s: (s["at"] or "", 0 if s["kind"] == "stage" else 1))
    furthest = max((FUNNEL.index(k) for k in reached if k in FUNNEL), default=-1)
    last_stage = next((s for s in reversed(steps) if s["kind"] == "stage"), None)
    from src.services.handover import current
    now = current(conv)
    ended = {"not_served", "not_eligible", "not_investing"}
    outcome = ("handed_over" if handed_at else
               "closed" if dz.group(now["key"]) == "negative" or (last_stage and last_stage["key"] in ended) else
               "in_progress")
    return {
        "phone": phone, "name": conv.profile_name, "steps": steps,
        "funnel": [{"key": k, "label": FUNNEL_LABELS[k], "at": reached.get(k)} for k in FUNNEL],
        "furthest": furthest, "outcome": outcome,
        "now": {"label": now["label"], "key": now["key"], "since": now["at"]},
        "last": {"what": last_stage["what"], "at": last_stage["at"]} if last_stage else None,
        "last_activity": steps[-1]["at"] if steps else None,
    }


def _plainly(conv: WhatsAppConversation, j: dict) -> dict:
    """The few things a list of leads needs to say at a glance."""
    cov = (conv.bot_data or {}).get("coverage") or {}
    stages = [s for s in j["steps"] if s["kind"] == "stage"]
    ended = next((s for s in reversed(stages) if s["key"] in ("not_served", "not_eligible", "not_investing")), None)
    if j["outcome"] == "handed_over":
        where = FUNNEL_LABELS["handed_over"]
    elif j["outcome"] == "closed":
        where = ended["what"] if ended else j["now"]["label"]
    else:
        where = FUNNEL_LABELS[FUNNEL[j["furthest"]]] if j["furthest"] >= 0 else "Not started"
    ours = next((s for s in reversed(j["steps"]) if s["action"] and s["tone"] != "planned"), None)
    planned = next((s for s in j["steps"] if s["tone"] == "planned"), None)
    started = next((f["at"] for f in j["funnel"] if f["key"] == "interested" and f["at"]), None)
    return {
        "where": where,
        "started_at": started,
        "place": ", ".join(x for x in (cov.get("district"), cov.get("state")) if x) or None,
        "pincode": cov.get("pincode"),
        "our_last": {"text": ours["action"], "at": ours["action_at"]} if ours else None,
        "next": {"text": planned["action"], "at": planned["at"]} if planned else None,
        "steps_done": max(j["furthest"], 0),
        "steps_total": len(FUNNEL) - 1,
    }


def board(db: Session, limit: int = 200) -> List[dict]:
    """Every campaign lead's journey in short, most recently active first."""
    from src.models.whatsapp import WhatsAppCampaignRecipient

    sent = {}
    for phone, at in (db.query(WhatsAppCampaignRecipient.phone, WhatsAppCampaignRecipient.sent_at)
                      .filter(WhatsAppCampaignRecipient.sent_at.isnot(None)).all()):
        if phone not in sent or inbox.aware(at) < inbox.aware(sent[phone]):
            sent[phone] = at
    convs = [c for c in db.query(WhatsAppConversation).all() if c.phone in sent or c.bot_step]
    phones = [c.phone for c in convs]
    if not phones:
        return []

    def grouped(model, order=None):
        out = defaultdict(list)
        q = db.query(model).filter(model.phone.in_(phones))
        if order is not None:
            q = q.order_by(order)
        for r in q.all():
            out[r.phone].append(r)
        return out

    messages = grouped(WhatsAppMessage, WhatsAppMessage.created_at)
    activities, followups, tickets = grouped(ChatActivity), grouped(FollowUp), grouped(AttentionTicket)
    rows = []
    for c in convs:
        j = build(db, c, messages=messages[c.phone], activities=activities[c.phone], followups=followups[c.phone],
                  tickets=tickets[c.phone], sent_at=sent.get(c.phone))
        # Only those who did something: a campaign that went unanswered is not a lead's journey yet.
        if j["furthest"] < 1 and not any(s["kind"] == "stage" and s["key"] != "campaign" for s in j["steps"]):
            continue
        row = {k: j[k] for k in ("phone", "name", "furthest", "outcome", "now", "last", "last_activity", "funnel")}
        row.update(_plainly(c, j))
        rows.append(row)
    rows.sort(key=lambda r: r["last_activity"] or "", reverse=True)
    return rows[:limit]
