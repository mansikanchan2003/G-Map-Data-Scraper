"""
A conversation at a glance, for whoever opens it in the inbox and for the
email sent when it needs attention: who the person is and where, how far
they got, what they asked (with the answers Eko's FAQ has for it), what else
they wrote, and what to send them next, ready to copy in their language.

Built from the conversation itself, not by a language model, so nobody's
messages leave our server and the summary says only what happened.
"""
import re
from datetime import timedelta, timezone
from typing import List

from sqlalchemy.orm import Session

from src.models import Business
from src.models.inbox import OnboardingDocument, WhatsAppConversation, WhatsAppMessage
from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient
from src.services import applications, eko_knowledge, inbox
from src.services import onboarding_bot as bot
from src.services.bot_messages import LANGUAGE_NAMES

IST = timezone(timedelta(hours=5, minutes=30))
# How many of the latest inbound messages are read for questions and the rest.
RECENT = 40
# Replies that answer the bot's own questions rather than say something new.
_ANSWER_WORDS = {"yes", "no", "haan", "han", "ha", "nahi", "nahin", "ok", "okay", "hmm", "thik", "theek",
                 "हाँ", "हां", "नहीं", "ठीक", "હા", "ના", "ਹਾਂ", "ਨਹੀਂ", "thanks", "thank", "dhanyavad", "shukriya"}
_PIN = re.compile(r"(?<!\d)[1-9]\d{5}(?!\d)")

STEP_NEXT = {
    None: ("They have not started. Greet them and invite them to tap Interested.", "greeting"),
    bot.CHOOSE_LANG: ("Waiting for them to choose a language. Ask them to pick one.", "language_prompt"),
    bot.AWAIT_PIN: ("Waiting for their PIN code. Ask for their 6-digit PIN.", "ask_pin"),
    bot.AWAIT_EDUCATION: ("Waiting for their education. Ask how far they have studied.", "ask_education"),
    bot.AWAIT_FRANCHISE: ("Waiting for the investment answer. Explain what up to ₹5 lakh is for, then ask.", "ask_invest"),
    bot.AWAIT_INVEST: ("Waiting for the investment answer. Explain what up to ₹5 lakh is for (devices, e-wallet, "
                       "setup) and ask whether they can invest it.", "ask_invest"),
    bot.AWAIT_DOCS: ("Waiting to hear whether they have the documents. Go through the list with them.", "ask_docs"),
    bot.AWAIT_UPLOAD: ("They have the upload link but have not submitted. Remind them, and offer help with "
                       "scanning or uploading.", None),
    bot.SUBMITTED: ("Documents submitted: a lead. Thank them and arrange the team's call for the next steps.", None),
    bot.NOT_SERVED: ("Their PIN is outside our area. Tell them, and note the PIN in case we expand there.", None),
    bot.NOT_ELIGIBLE: ("Below 12th, so not eligible for the Banking Outlet. Thank them politely.", None),
    bot.NOT_INVESTING: ("They said they cannot invest. Explain that the money stays theirs in their e-wallet "
                        "and ask whether up to ₹5 lakh could work.", "invest_explained"),
    bot.HANDOVER: ("The bot handed them over after three unusable PIN codes. Call them or ask for the PIN again.", "ask_pin"),
    bot.AWAIT_WEBINAR: ("Asked about personal guidance. Ask whether they can join.", None),
    bot.AWAIT_AVAILABILITY: ("Waiting for when they can join personal guidance. Ask for a day and time.", None),
    bot.WEBINAR_CONFIRMED: ("Confirmed for personal guidance. Contact them with the time.", None),
    bot.WEBINAR_AVAILABILITY: ("Shared when they can join personal guidance. Contact them then.", None),
}


def _when(at) -> str:
    at = inbox.aware(at)
    return at.astimezone(IST).strftime("%d %b, %I:%M %p") if at else ""


def _person(db: Session, conv: WhatsAppConversation) -> dict:
    data = conv.bot_data or {}
    coverage = data.get("coverage") or {}
    typed = data.get("typed_pin") or {}
    pin = coverage.get("pincode") or typed.get("pincode") or applications._typed_pins(db, [conv]).get(conv.phone)
    geo = (coverage.get("geo") if coverage.get("pincode") else typed.get("geo")) or {}
    business = db.query(Business).filter(Business.phone == conv.phone).first()
    source = applications._sources(db, [conv.phone]).get(conv.phone) or {}
    return {
        "name": conv.profile_name,
        "phone": conv.phone,
        "pincode": pin,
        "tehsil": geo.get("tehsil") or (business.tehsil if business else None),
        "district": geo.get("district") or source.get("district") or (business.district if business else None),
        "state": geo.get("state") or source.get("state") or (business.state if business else None),
        "category": source.get("category") or (business.category if business else None),
        "business_name": source.get("business_name"),
        "campaign": source.get("campaign"),
        "language": LANGUAGE_NAMES.get(data.get("lang")) if data.get("lang") else None,
    }


def _story(db: Session, conv: WhatsAppConversation) -> List[str]:
    """How far they got, step by step, in plain words."""
    data = conv.bot_data or {}
    out = []
    reached = (db.query(WhatsAppCampaignRecipient, WhatsAppCampaign)
               .join(WhatsAppCampaign, WhatsAppCampaign.campaign_id == WhatsAppCampaignRecipient.campaign_id)
               .filter(WhatsAppCampaignRecipient.phone == conv.phone, WhatsAppCampaignRecipient.sent_at.isnot(None))
               .order_by(WhatsAppCampaignRecipient.sent_at).all())
    if reached:
        r, c = reached[-1]
        out.append(f"Reached by the campaign “{c.name}” on {_when(r.sent_at)}"
                   + (f" ({len(reached)} campaigns in all)" if len(reached) > 1 else "") + ".")
    if data.get("trigger"):
        out.append(f"Tapped “{data['trigger']}”.")
    if data.get("lang"):
        out.append(f"Chose {LANGUAGE_NAMES.get(data['lang'], data['lang'])}.")
    coverage = data.get("coverage") or {}
    if coverage.get("pincode"):
        served = applications._served(conv)
        out.append(f"Gave PIN {coverage['pincode']}: " + ("in our area" if served else "outside our area")
                   + (f" (nearest of ours {coverage['nearest_pincode']}, {coverage.get('distance_km')} km)"
                      if coverage.get("nearest_pincode") and coverage.get("nearest_pincode") != coverage["pincode"]
                      else "") + ".")
    edu = data.get("education")
    if edu:
        out.append({"12": "Studied to 12th/Diploma.", "grad": "Graduate or post-graduate.",
                    "other": "Below 12th: not eligible."}.get(edu, f"Education: {edu}."))
    if data.get("can_invest") is not None:
        out.append("Can invest up to ₹5 lakh." if data["can_invest"] else "Said they cannot invest up to ₹5 lakh.")
    docs = db.query(OnboardingDocument).filter(OnboardingDocument.phone == conv.phone).count()
    if conv.documents_submitted_at:
        out.append(f"Submitted {docs} documents on {_when(conv.documents_submitted_at)}: a lead.")
    elif conv.upload_token:
        out.append("Was sent the upload link" + (f"; {docs} documents uploaded so far" if docs else "; nothing uploaded yet") + ".")
    guidance = data.get("webinar") or {}
    if guidance.get("answer") == "yes":
        out.append("Confirmed for personal guidance.")
    elif guidance.get("availability"):
        out.append(f"For personal guidance, available: {guidance['availability']}.")
    if data.get("faq_answered"):
        out.append("The bot answered from the FAQ: " + ", ".join(sorted(set(data["faq_answered"]))) + ".")
    return out


def summarise(db: Session, conv: WhatsAppConversation) -> dict:
    """Everything the summary panel and the attention email show."""
    data = conv.bot_data or {}
    lang = data.get("lang") or "en"
    messages = (db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == conv.phone, WhatsAppMessage.direction == "IN")
                .order_by(WhatsAppMessage.created_at.desc()).limit(RECENT).all())[::-1]
    answered = set(data.get("faq_answered") or [])

    questions, other = [], []
    for m in messages:
        said = bot.message_text(m)
        voice = m.kind == "audio"
        if voice and not said:
            other.append({"text": "(voice note, not transcribed: listen in the chat)", "at": _when(m.created_at), "voice": True})
            continue
        if not said:
            continue
        plain = said.strip()
        words = re.findall(r"\w+", plain.lower())
        faq = eko_knowledge.match(plain)
        if faq or bot.looks_like_question(plain):
            questions.append({
                "text": plain, "at": _when(m.created_at), "voice": voice,
                "answers": [{"question": eko_knowledge._BY_ID[i]["question"],
                             "answer": eko_knowledge.answer(i, lang, plain)} for i in faq],
                "answered_by_bot": bool(faq) and set(faq) <= answered,
            })
        elif _PIN.search(plain) or (words and all(w in _ANSWER_WORDS for w in words)):
            continue  # a PIN or a yes/no: an answer to the bot, already in the story
        else:
            other.append({"text": plain, "at": _when(m.created_at), "voice": voice})

    step_text, key = STEP_NEXT.get(conv.bot_step, STEP_NEXT[None])
    open_window = bool(conv.last_inbound_at and inbox.now() - inbox.aware(conv.last_inbound_at) < inbox.REPLY_WINDOW)
    reply = None
    unanswered = [q for q in questions if q["answers"] and not q["answered_by_bot"]]
    if unanswered:
        reply = "\n\n".join(a["answer"] for a in unanswered[-1]["answers"])
    elif key:
        try:
            reply = bot._t(db, conv, key) if key != "greeting" else None
        except Exception:
            reply = None
    if conv.bot_step == bot.AWAIT_UPLOAD and conv.upload_token:
        reply = bot._t(db, conv, "send_link") + "\n" + bot.upload_url(conv)

    needing = [q for q in questions if not q["answers"]]
    headline = conv.bot_step and bot.STEP_LABELS.get(conv.bot_step, conv.bot_step) or "Has not started"
    if conv.needs_attention:
        headline += " · needs attention"
    from src.services import tickets
    ticket = tickets.open_ticket(db, conv.phone) if conv.needs_attention else None
    return {
        "generated_at": inbox.now().isoformat(),
        "ticket_id": ticket.ticket_id if ticket else None,
        "person": _person(db, conv),
        "headline": headline,
        "story": _story(db, conv),
        "questions": questions[-6:],
        "unanswered_questions": len(needing),
        "other_messages": other[-6:],
        "attention": {"reason": conv.attention_reason, "at": _when(conv.attention_at)} if conv.needs_attention else None,
        "next": {
            "action": step_text if open_window else step_text + " The 24-hour window is closed: only a campaign template can reach them now.",
            "reply": reply if open_window else None,
            "reply_language": LANGUAGE_NAMES.get(lang, lang),
            "window_open": open_window,
        },
    }


def as_text(s: dict) -> str:
    """The summary as plain text, for the attention email."""
    p = s["person"]
    place = ", ".join(x for x in (p["tehsil"], p["district"], p["state"]) if x)
    lines = ([f"Ticket:    {s['ticket_id']} (raised)", ""] if s.get("ticket_id") else []) + [
        f"Name:      {p['name'] or '—'}",
        f"Phone:     {p['phone']}",
        f"PIN code:  {p['pincode'] or '—'}",
        f"Tehsil:    {p['tehsil'] or '—'}",
        f"District:  {p['district'] or '—'}",
        f"State:     {p['state'] or '—'}",
    ]
    if p.get("category") or p.get("business_name"):
        lines.append(f"Business:  {', '.join(x for x in (p.get('business_name'), p.get('category')) if x)}")
    if p.get("campaign"):
        lines.append(f"Campaign:  {p['campaign']}")
    if p.get("language"):
        lines.append(f"Language:  {p['language']}")
    lines += ["", f"WHERE THEY ARE: {s['headline']}"]
    if s.get("attention"):
        lines.append(f"Why it needs attention: {s['attention']['reason'] or 'marked for the team'} ({s['attention']['at']})")
    lines += ["", "WHAT HAPPENED"] + [f"- {x}" for x in s["story"] or ["Nothing yet."]]
    lines += ["", "WHAT THEY ASKED"]
    if not s["questions"]:
        lines.append("- No questions.")
    for q in s["questions"]:
        tag = " (voice note, machine transcript)" if q["voice"] else ""
        lines.append(f"- “{q['text']}”{tag} · {q['at']}")
        if q["answers"]:
            for a in q["answers"]:
                lines.append(f"    Possible answer ({a['question']}): {a['answer']}"
                             + ("  [the bot already sent this]" if q["answered_by_bot"] else ""))
        else:
            lines.append("    No ready answer in the FAQ: please reply yourself.")
    if s["other_messages"]:
        lines += ["", "OTHER MESSAGES (not a question or an answer to the bot)"]
        lines += [f"- “{o['text']}” · {o['at']}" for o in s["other_messages"]]
    lines += ["", "WHAT TO DO NEXT", f"- {s['next']['action']}"]
    if s["next"]["reply"]:
        lines += [f"- A reply you could send ({s['next']['reply_language']}):", "", s["next"]["reply"]]
    return "\n".join(lines)
