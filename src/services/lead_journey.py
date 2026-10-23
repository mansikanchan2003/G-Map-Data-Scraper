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
from collections import Counter, defaultdict
from datetime import datetime, timedelta
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
    # Nudges a follow-up sent are shown as that follow-up, not again as a bot reply; a bot
    # reply that itself served as one (the upload link, the cannot-invest answer) stays a step.
    nudge_ids = {f.message_id for f in followups if f.message_id and f.note != "Said in the bot's reply"}
    for m in sorted(messages, key=lambda x: inbox.aware(x.created_at)):
        if m.direction == "IN":
            last_in, answered_since_in = m, False
            continue
        if m.message_id in nudge_ids:
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
            if key == "ask_education" and ((conv.bot_data or {}).get("coverage") or {}).get("served") is False:
                what, tone = ("Shared a PIN code outside our SBI branch area: not qualified for SBI branch code, "
                              "kept for another proposal"), "neutral"
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
        "open": open_items(followups, tickets),
        "dispositions": disposition_actions(conv, activities, followups, tickets, steps),
        "whats_next": whats_next(conv, followups, messages),
        "funnel": [{"key": k, "label": FUNNEL_LABELS[k], "at": reached.get(k)} for k in FUNNEL],
        "furthest": furthest, "outcome": outcome,
        "now": {"label": now["label"], "key": now["key"], "since": now["at"]},
        "last": {"what": last_stage["what"], "at": last_stage["at"]} if last_stage else None,
        "last_activity": steps[-1]["at"] if steps else None,
    }


OWNER_LABEL = {"bot": "Bot", "human": "Team (Human)", "dc": "District Coordinator", dz.API: dz.HANDED_TO}


def team_names() -> str:
    """Who "the team" is, by name: the people a hand-over to a person is emailed to (the user, 2026-10-22)."""
    from src.services import auth_service, notifier
    return ", ".join(_who(e) for e in notifier.team(auth_service.BOOTSTRAP_ADMIN).split(", ") if e)


def owner_label(owner: str, done_by: Optional[str] = None) -> str:
    """An action item's owner by name: whoever did it, or for the team, who it falls to."""
    if done_by and done_by != "bot":
        return _who(done_by)
    if owner == "human":
        return f"Team: {team_names()}"
    return OWNER_LABEL.get(owner, owner)
# A planned item this late is counted as missed.
LATE = timedelta(hours=1)
WAITING_LATE = timedelta(days=1)


def _item(f: FollowUp, now: datetime) -> dict:
    """One action item as the lead's disposition panel shows it: what, whose, and done, planned or missed."""
    due = inbox.aware(f.due_at)
    if f.wants == dz.API:
        text, owner = f"Hand the lead over to {dz.HANDED_TO}", dz.API
    elif f.wants == dz.TASK:
        text, owner = f.task or "Task", f.owner
    else:
        text, owner = f"WhatsApp message to {dz.PURPOSE_PLAIN.get(f.purpose, f.purpose.replace('_', ' '))}", "bot"
        if f.owner == dz.HUMAN:
            text += f" (the sheet's call by {team_names()}; a nudge until calling is on)"
    when, result = _iso(f.done_at or f.sent_at or f.due_at), None
    if f.status in ("sent", "replied", "no_answer", "done"):
        status = "done"
        result = {"sent": "Sent", "replied": "Sent · they replied",
                  "no_answer": "Sent · no reply in a day (RNR)", "done": f"Done by {_who(f.done_by)}" if f.done_by else "Done"}[f.status]
        if f.wants == dz.API and f.status == "sent":
            result = f"Sent to {dz.HANDED_TO}"
    elif f.status == "failed":
        status, result = "missed", f.note or "Could not be sent"
    elif f.status == "cancelled":
        status, result = "cancelled", f.note or "Not needed"
    elif f.status == "waiting":
        late = due and now - due >= WAITING_LATE
        status = "missed" if late else "planned"
        if f.wants == dz.API:
            result = f.note or "Waiting"
        else:
            # Plain words: the channel notes ("WhatsApp calling is not switched on...") are for the logs.
            result = ("Their 24-hour window is shut: waiting for Meta to approve its template"
                      + (" (over a day)" if late else ""))
        when = _iso(f.due_at)
    else:  # scheduled
        late = due and now - due >= LATE
        status = "missed" if late else "planned"
        result = "Overdue: not sent yet" if late else ("Due now" if due and due <= now else "Planned")
        when = _iso(f.due_at)
    return {"text": text, "owner": owner, "owner_label": owner_label(owner, f.done_by if f.status == "done" else None),
            "status": status, "when": when, "result": result, "attempt": f.attempt}


# The disposition each stage of the bot's questions stands for. The bot does
# not record these as it goes; they are read from the chat's steps, so every
# lead, older ones too, shows the bot's dispositions and what it did in each
# (the user, 2026-10-22).
STAGE_DISPOSITION = {
    "interested": "int_in_bot_flow", "wrote_in": "int_in_bot_flow", "language": "int_in_bot_flow",
    "pin": "int_in_bot_flow", "education": "int_in_bot_flow", "investment": "int_in_bot_flow",
    "guidance": "int_more_info", "docs_ready": "int_docs_pending", "docs_later": "int_docs_pending",
    "uploaded": "int_visit", "handed_over": "int_visit",
    "not_served": "int_not_sbi", "not_eligible": "rej_eligibility", "not_investing": "ni_investment",
}


def _bot_blocks(steps: List[dict], recorded: List[ChatActivity]) -> List[dict]:
    """
    The bot's dispositions, read from the chat's steps: one per change, with
    the bot's own actions in it as done action items.
    """
    blocks: List[dict] = []
    for st in steps:
        if st["kind"] == "stage" and st["key"] in STAGE_DISPOSITION:
            key = STAGE_DISPOSITION[st["key"]]
            if st["key"] == "pin" and "not qualified for SBI" in (st["what"] or ""):
                key = "int_not_sbi"
            if blocks and blocks[-1]["key"] == key:
                continue
            # The bot records some itself now (cannot invest): not shown twice.
            if any(dz.normalise(a.value) == key and a.by == "bot" and st["at"]
                   and abs((inbox.aware(a.at) - datetime.fromisoformat(st["at"])).total_seconds()) < 600 for a in recorded):
                continue
            s = dz.sub(key)
            cat = dz.category_of(key)
            blocks.append({"key": key, "label": dz.label(key), "category": cat.label if cat else None,
                           "group": dz.group(key), "recorded_at": st["at"], "recorded_by": "Bot",
                           "note": st["what"], "sheet_action": s.action if s else None,
                           "sheet_owner": s.owner if s else None, "current": False, "items": [], "derived": True})
    return blocks


def _trust_answer(at) -> dict:
    return {"text": "Answered who Eko is, with the website link and our number to call", "owner": "bot",
            "owner_label": OWNER_LABEL["bot"], "status": "done", "when": _iso(at), "result": "Sent", "attempt": 1}


TRUST_TICKET = "Call this lead: trust concern"


def _trust_blocks(tickets: List[AttentionTicket], recorded: List[ChatActivity], now: datetime) -> List[dict]:
    """
    "Trust concern" for chats from before the bot recorded it (23 Oct 2026),
    read from the ticket its trust answer raised: the answer, the team told,
    and the team's call (done when the ticket was solved).
    """
    s = dz.SUBS["int_trust"]
    out = []
    for t in tickets:
        asked = next((q for q in (t.latest_question, t.question) if q and q.startswith(TRUST_TICKET)), None)
        if not asked:
            continue
        at = inbox.aware(t.raised_at)
        if any(dz.normalise(a.value) == "int_trust" and abs((inbox.aware(a.at) - at).total_seconds()) < 600
               for a in recorded):
            continue
        solved = bool(t.resolved_at)
        call = {"text": "Call them about their trust concern", "owner": "human",
                "owner_label": owner_label("human", t.resolved_by if solved else None),
                "status": "done" if solved else ("missed" if now - at >= WAITING_LATE else "planned"),
                "when": _iso(t.resolved_at or t.raised_at),
                "result": (f"Ticket solved by {_who(t.resolved_by)}" if solved
                           else "Not done yet: the ticket is open"), "attempt": 1}
        told = {"text": f"Tell the team: ticket and email to {team_names()}", "owner": "human",
                "owner_label": owner_label("human"), "status": "done", "when": _iso(t.raised_at),
                "result": "Ticket raised and emailed", "attempt": 1}
        out.append({"key": "int_trust", "label": s.label, "category": dz.category_of("int_trust").label,
                    "group": dz.group("int_trust"), "recorded_at": _iso(t.raised_at), "recorded_by": "Bot",
                    "note": asked[len(TRUST_TICKET):].lstrip(". ") or None, "sheet_action": s.action,
                    "sheet_owner": s.owner, "current": False, "items": [_trust_answer(t.raised_at), told, call],
                    "derived": True})
    return out


def _attach_bot_actions(blocks: List[dict], steps: List[dict]) -> None:
    """The bot's own actions, done, under whichever disposition was current when it did them."""
    for st in steps:
        if not st["action"] or st["tone"] == "planned" or (st["by"] and st["by"] not in ("bot", dz.HANDED_TO)):
            continue
        if st["key"].startswith("disposition:") or st["key"] in ("to_person", "to_bot", "team_reply", "task", "nudge",
                                                                  "ticket_solved"):
            continue
        at = st["action_at"] or st["at"]
        home = None
        for b in blocks:
            start = b.get("_start") or b["recorded_at"]
            if start and at and start <= at:
                home = b
        if home is None:
            continue
        home["items"].append({"text": st["action"], "owner": dz.API if st["by"] == dz.HANDED_TO else "bot",
                              "owner_label": dz.HANDED_TO if st["by"] == dz.HANDED_TO else OWNER_LABEL["bot"],
                              "status": "done", "when": at, "result": st["what"], "attempt": 1})


def disposition_actions(conv: WhatsAppConversation, activities: List[ChatActivity], followups: List[FollowUp],
                        tickets: List[AttentionTicket], steps: Optional[List[dict]] = None) -> List[dict]:
    """
    Each disposition this lead has had, newest first, with the sheet's action
    and owner, and every action item it called for: done, planned or missed,
    and whose. The bot's own dispositions (its stages) come from the chat's
    steps, with what it did in each.
    """
    now = inbox.now()
    records = sorted((a for a in activities if a.kind == "disposition"), key=lambda a: inbox.aware(a.at))
    out = []
    for i, a in enumerate(records):
        key = dz.normalise(a.value)
        s = dz.sub(key)
        start = inbox.aware(a.at) - timedelta(minutes=1)
        end = inbox.aware(records[i + 1].at) - timedelta(minutes=1) if i + 1 < len(records) else None
        mine = [f for f in followups if dz.normalise(f.disposition) == key
                and inbox.aware(f.created_at) >= start and (end is None or inbox.aware(f.created_at) < end)]
        items = [_item(f, now) for f in sorted(mine, key=lambda f: inbox.aware(f.due_at))]
        if s and dz.needs_team(s):
            ticket = next((t for t in tickets if inbox.aware(t.raised_at) >= start), None)
            items.insert(0, {"text": f"Tell the team: ticket and email to {team_names()}", "owner": "human",
                             "owner_label": owner_label("human", ticket.resolved_by if ticket and ticket.resolved_at else None),
                             "status": "done", "when": _iso(ticket.raised_at if ticket else a.at),
                             "result": ("Ticket raised" + (f" · solved by {'the bot' if ticket.resolved_by == 'bot' else _who(ticket.resolved_by)}"
                                                           if ticket and ticket.resolved_at else "")) if ticket
                             else "Email sent (recorded while solving a ticket, so no new one)", "attempt": 1})
        if key == "int_trust" and a.by == "bot":
            items.insert(0, _trust_answer(a.at))
        if s and s.steps and not mine and not s.closes:
            items.append({"text": s.action or "Its follow-up", "owner": "bot", "owner_label": OWNER_LABEL["bot"],
                          "status": "missed", "when": _iso(a.at),
                          "result": "Never set up (recorded before action items were automatic, or it failed)",
                          "attempt": 1})
        if s and s.closes and not s.stage:
            items.append({"text": "Close the lead: send nothing more", "owner": "bot", "owner_label": OWNER_LABEL["bot"],
                          "status": "done", "when": _iso(a.at), "result": "Closed", "attempt": 1})
        cat = dz.category_of(key)
        out.append({
            "key": key, "label": dz.label(key) or a.value, "category": cat.label if cat else None,
            "group": dz.group(key), "recorded_at": _iso(a.at),
            "recorded_by": "Bot" if a.by == "bot" else _who(a.by), "note": a.note,
            "sheet_action": s.action if s else None, "sheet_owner": s.owner if s else None,
            "current": i == len(records) - 1, "items": items,
        })
    for b in out:
        b["derived"] = False
    out += _bot_blocks(steps or [], records)
    out += _trust_blocks(tickets, records, now)
    out.sort(key=lambda b: b["recorded_at"] or "")
    # A disposition the bot records itself starts with the message that brought it on
    # (the upload link, the cannot-invest reply), sent a moment before it was recorded.
    for b in out:
        if b["recorded_by"] == "Bot" and not b.get("derived") and b["recorded_at"]:
            rec = datetime.fromisoformat(b["recorded_at"])
            for st in steps or []:
                if (st["kind"] == "stage" and STAGE_DISPOSITION.get(st["key"]) == b["key"] and st["action_at"]
                        and timedelta(0) <= rec - datetime.fromisoformat(st["action_at"]) <= timedelta(minutes=1)):
                    b["_start"] = st["action_at"]
    _attach_bot_actions(out, steps or [])
    for b in out:
        b.pop("_start", None)
    for b in out:
        b["items"].sort(key=lambda i: i["when"] or "")
    if not out:
        from src.services.handover import current
        now_d = current(conv)
        cat = dz.category_of(now_d["key"])
        out.append({"key": now_d["key"], "label": now_d["label"], "category": cat.label if cat else None,
                    "group": dz.group(now_d["key"]), "recorded_at": now_d["at"], "recorded_by": "Read from the bot's step",
                    "note": None, "sheet_action": None, "sheet_owner": None, "current": True, "items": [], "derived": True})
    out.sort(key=lambda b: b["recorded_at"] or "")
    for i, b in enumerate(out):
        b["current"] = i == len(out) - 1
    out.reverse()
    return out


def whats_next(conv: WhatsAppConversation, followups: List[FollowUp], messages: List[WhatsAppMessage]) -> List[dict]:
    """
    What comes next for a lead, soonest first: action items already planned,
    what the bot is waiting for them to do and its reminder if one is due,
    and the disposition expected next. Says so when nothing is planned.
    """
    from src.services import nudges, onboarding_bot as bot

    # What the bot waits for at each step (the Inbox summary says the same in Hinglish).
    _WAITING = {
        bot.CHOOSE_LANG: "choose a language",
        bot.AWAIT_PIN: "send their PIN code",
        bot.AWAIT_EDUCATION: "say how far they have studied",
        bot.AWAIT_FRANCHISE: "say whether they can invest up to ₹5 lakh",
        bot.AWAIT_INVEST: "say whether they can invest up to ₹5 lakh",
        bot.AWAIT_DOCS: "say whether they have the documents",
        bot.AWAIT_UPLOAD: "upload their documents",
        bot.GUIDANCE_QA: "ask their questions, or tap Interested to start",
        bot.AWAIT_WEBINAR: "say whether they can join personal guidance",
        bot.AWAIT_AVAILABILITY: "say when they can join personal guidance",
    }

    now = inbox.now()
    out = []
    for f in followups:
        if f.status in ("scheduled", "waiting"):
            item = _item(f, now)
            out.append({"kind": "action", "text": item["text"], "owner_label": item["owner_label"],
                        "when": _iso(f.due_at), "note": item["result"] if item["status"] == "planned" else "Overdue"})
    step = conv.bot_step
    if conv.documents_submitted_at:
        out.append({"kind": "disposition", "text": f"With {dz.HANDED_TO}: AutoGMap's part is done",
                    "owner_label": dz.HANDED_TO, "when": None, "note": dz.SUBS["int_visit"].action})
    elif conv.bot_paused:
        out.append({"kind": "waiting", "text": "A person is handling the chat; the bot waits until it is handed back",
                    "owner_label": owner_label("human", conv.handled_by), "when": None, "note": None})
    elif step in _WAITING:
        out.append({"kind": "waiting", "text": f"Waiting for them to {_WAITING[step]}", "owner_label": "Lead",
                    "when": None, "note": None})
        last = max(messages, key=lambda m: inbox.aware(m.created_at), default=None)
        if (step in bot.NUDGE_STEPS and last is not None and last.direction == "OUT" and last.sent_by == "bot"
                and last.message_id != (conv.bot_data or {}).get("nudge_message_id")):
            due = inbox.aware(last.created_at) + nudges.AFTER
            shut = inbox.window_expires_at(conv)
            if shut and due < shut - nudges.WINDOW_MARGIN:
                out.append({"kind": "action", "text": "Reminder with the same question, if they stay quiet",
                            "owner_label": OWNER_LABEL["bot"], "when": _iso(due), "note": None})
        nxt = ("int_visit" if step in (bot.AWAIT_DOCS, bot.AWAIT_UPLOAD)
               else "int_in_bot_flow" if step == bot.GUIDANCE_QA else "int_docs_pending")
        when = {"int_visit": "once they upload their documents",
                "int_docs_pending": "once they say their documents are ready (the upload link goes out)",
                "int_in_bot_flow": "once they tap Interested"}[nxt]
        label = (f"{dz.label(nxt)}: handed to {dz.HANDED_TO}" if nxt == "int_visit" else dz.label(nxt))
        out.append({"kind": "disposition", "text": f"Next disposition: {label}", "owner_label": OWNER_LABEL["bot"],
                    "when": None, "note": when})
    if not any(o["kind"] == "action" for o in out) and not conv.documents_submitted_at:
        out.append({"kind": "none", "text": "No action item planned", "owner_label": owner_label("human"), "when": None,
                    "note": "Record a disposition that sets a follow-up (a callback, a check-in date...) so nothing is forgotten"})
    rank = {"action": 0, "waiting": 1, "disposition": 2, "none": 3}
    return sorted(out, key=lambda o: (rank[o["kind"]], o["when"] or ""))


def action_counts(blocks: List[dict]) -> dict:
    """How many of a lead's action items are done, planned and missed, across its dispositions."""
    c = Counter(i["status"] for b in blocks for i in b["items"])
    return {k: c.get(k, 0) for k in ("done", "planned", "missed")}


def open_items(followups: List[FollowUp], tickets: List[AttentionTicket]) -> List[dict]:
    """
    Everything still to be done for a lead, soonest first: nudges planned or
    waiting, the team's and the District Coordinator's tasks, a question
    waiting for the team, and the hand-over to Eko Acquisition if it has not
    gone yet.
    """
    out = []
    for f in followups:
        if f.wants == dz.API:
            if f.status in ("scheduled", "waiting", "failed"):
                out.append({"kind": "handover", "text": f"Hand-over to {dz.HANDED_TO}",
                            "status": "failed" if f.status == "failed" else "waiting", "owner": "bot",
                            "due": _iso(f.due_at), "since": _iso(f.created_at), "note": f.note})
        elif f.status not in ("scheduled", "waiting"):
            continue
        elif f.wants == dz.TASK:
            owner = {"human": "The team", "dc": "District Coordinator"}.get(f.owner, f.owner)
            out.append({"kind": "task", "text": f"{owner}: {f.task}", "status": "open", "owner": f.owner,
                        "due": _iso(f.due_at), "since": _iso(f.created_at), "note": None})
        else:
            out.append({"kind": "nudge",
                        "text": f"WhatsApp message to {dz.PURPOSE_PLAIN.get(f.purpose, f.purpose.replace('_', ' '))}",
                        "status": f.status, "owner": f.owner, "due": _iso(f.due_at), "since": _iso(f.created_at),
                        "note": "Waiting for Meta to approve its template" if f.status == "waiting" else None})
    for t in tickets:
        if not t.resolved_at:
            out.append({"kind": "ticket", "text": f"Question for the team: “{(t.latest_question or t.question or '').strip()[:140]}”",
                        "status": "open", "owner": "human", "due": None, "since": _iso(t.raised_at), "note": None})
    return sorted(out, key=lambda o: o["due"] or o["since"] or "")


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
        row = {k: j[k] for k in ("phone", "name", "furthest", "outcome", "now", "last", "last_activity", "funnel", "open")}
        row["actions"] = action_counts(j["dispositions"])
        row.update(_plainly(c, j))
        rows.append(row)
    rows.sort(key=lambda r: r["last_activity"] or "", reverse=True)
    return rows[:limit]


# The groups a disposition mix is told in, and those a campaign reached who
# have not answered yet.
MIX_GROUPS = ("positive", "follow_up", "negative", "other", "no_reply")
NO_REPLY = "No reply yet"


def disposition_mix(db: Session) -> dict:
    """
    Where the people each campaign, template and state reached stand now:
    each person's current disposition (as in the Inbox), counted under the
    latest campaign sent to them, its template, and their business's state.
    Test campaigns are left out. Someone who never wrote back and has no
    recorded disposition is "No reply yet".
    """
    from src.models import Business
    from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient, WhatsAppTemplate
    from src.services import campaign_insights as ci
    from src.services.handover import current

    tests = ci.test_campaign_ids(db)
    latest = {}
    for r in (db.query(WhatsAppCampaignRecipient).filter(WhatsAppCampaignRecipient.sent_at.isnot(None)).all()):
        if r.campaign_id in tests:
            continue
        phone = inbox.normalize_phone(r.phone)
        if phone not in latest or inbox.aware(r.sent_at) > inbox.aware(latest[phone].sent_at):
            latest[phone] = r
    campaigns = {c.campaign_id: c for c in db.query(WhatsAppCampaign).all()}
    templates = {t.template_id: t.name for t in db.query(WhatsAppTemplate).all()}
    convs = {c.phone: c for c in db.query(WhatsAppConversation).filter(WhatsAppConversation.phone.in_(list(latest))).all()} \
        if latest else {}
    by_id = {b.business_id: b for b in db.query(Business).filter(
        Business.business_id.in_([r.business_id for r in latest.values() if r.business_id])).all()}
    by_phone = {}
    for b in db.query(Business).filter(Business.phone.in_([r.phone for r in latest.values() if not r.business_id])).all():
        by_phone.setdefault(b.phone, b)

    rows = {"campaign": {}, "template": {}, "state": {}}
    for phone, r in latest.items():
        c = campaigns.get(r.campaign_id)
        b = by_id.get(r.business_id) if r.business_id else by_phone.get(r.phone)
        conv = convs.get(phone)
        if conv and (conv.last_inbound_at or conv.disposition):
            now = current(conv)
            group, label = dz.group(now["key"]), now["label"] or now["key"]
        else:
            group, label = "no_reply", NO_REPLY
        for dim, value in (("campaign", c.name if c else "(deleted campaign)"),
                           ("template", templates.get(c.template_id) if c and c.template_id else "(no template)"),
                           ("state", (b.state if b else None) or "Unknown")):
            row = rows[dim].setdefault(value or "Unknown", {"value": value or "Unknown", "sent": 0, "replied": 0,
                                                            "groups": {g: 0 for g in MIX_GROUPS},
                                                            "dispositions": Counter()})
            row["sent"] += 1
            row["replied"] += group != "no_reply"
            row["groups"][group] += 1
            row["dispositions"][(label, group)] += 1

    def out(row: dict) -> dict:
        return {**row, "dispositions": [{"label": l, "group": g, "count": n}
                                        for (l, g), n in row["dispositions"].most_common()]}

    return {dim: sorted((out(r) for r in v.values()), key=lambda r: -r["sent"]) for dim, v in rows.items()}
