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
    bot.NOT_INVESTING: ("They said they cannot invest. Explain that part of the money stays theirs in their e-wallet "
                        "and ask whether up to ₹5 lakh could work.", "invest_explained"),
    bot.HANDOVER: ("The bot handed them over after three unusable PIN codes. Call them or ask for the PIN again.", "ask_pin"),
    bot.AWAIT_WEBINAR: ("Asked about personal guidance. Ask whether they can join.", None),
    bot.AWAIT_AVAILABILITY: ("Waiting for when they can join personal guidance. Ask for a day and time.", None),
    bot.WEBINAR_CONFIRMED: ("Confirmed for personal guidance. Contact them with the time.", None),
    bot.WEBINAR_AVAILABILITY: ("Shared when they can join personal guidance. Contact them then.", None),
}


# What someone writing to us directly (not from a campaign) is most likely
# about, from the words they use: (topic, what the team should do).
_TOPICS = [
    ("installing or setting up a device", ("install", "istall", "instal", "device", "machine", "biometric",
                                           "fingerprint", "finger", "scanner", "printer", "setup", "set up", "मशीन",
                                           "डिवाइस", "इंस्टॉल"),
     "If they already run a CSP, pass it to the support team for the device or installation."),
    ("an ATM or a card", ("atm", "card", "debit", "kard", "एटीएम", "कार्ड"),
     "Ask for their CSP ID and pass it to the support team."),
    ("money, a payment or a transaction", ("commission", "payment", "paisa", "paise", "settlement", "wallet",
                                            "balance", "refund", "transaction", "txn", "credit", "debited", "amount",
                                            "पैसा", "पैसे", "कमीशन", "भुगतान"),
     "Ask for their CSP ID and the transaction details, and pass it to the support or accounts team."),
    ("logging in or their ID", ("login", "log in", "password", "otp", "user id", "userid", "blocked", "block",
                                "लॉगिन", "पासवर्ड"),
     "Ask for their CSP ID and pass it to the support team."),
    ("their CSP agreement, certificate or papers", ("agreement", "certificate", "renew", "valid", "expire", "iibf",
                                                   "एग्रीमेंट", "सर्टिफिकेट"),
     "Check what they need about their papers and pass it to the support team."),
    # "CSP" alone is mostly someone who already runs one, so it is not a sign here.
    ("becoming a CSP (opening a banking outlet)", ("kiosk kholna", "kiosk chahiye", "csp chahiye", "csp banna",
                                                  "franchise", "apply", "join", "mini bank", "mini branch",
                                                  "banking point", "कियोस्क खोलना", "फ्रेंचाइज़ी", "जुड़ना", "ખોલવું"),
     "They may want to open a banking outlet: send them the greeting so the bot can take them through it."),
]
_MEDIA_WORDS = {"image": ("photo", "photos"), "document": ("document", "documents"), "video": ("video", "videos"),
                "sticker": ("sticker", "stickers"), "location": ("location", "locations"),
                "contacts": ("contact card", "contact cards"), "audio": ("voice note", "voice notes")}
DIRECT_REPLY = {
    "action_none": "Read what they sent and reply. They are not in the onboarding flow; if they already run a CSP "
                   "and have a problem, pass it to the support team.",
}


def _media(kind: str, n: int = 1) -> str:
    one, many = _MEDIA_WORDS.get(kind, ("message the inbox cannot show", "messages the inbox cannot show"))
    return f"{'a' if n == 1 else n} {one if n == 1 else many}"


def _caption(m) -> str:
    """The words with a photo or document: its caption or file name, without the [Photo] label."""
    return re.sub(r"^\[[^\]]*\]\s*", "", m.body or "").strip()


def is_direct(db: Session, conv: WhatsAppConversation) -> bool:
    """Whether they wrote to us on their own: no campaign reached them and they never started the bot's flow."""
    if conv.bot_step or (conv.bot_data or {}).get("trigger"):
        return False
    return not (db.query(WhatsAppCampaignRecipient.recipient_id)
                .filter(WhatsAppCampaignRecipient.phone == conv.phone, WhatsAppCampaignRecipient.sent_at.isnot(None))
                .first())


def topics(texts: List[str]) -> List[tuple]:
    """The likely subjects of what they wrote, most mentioned first: [(topic, advice)]."""
    said = " " + " ".join(texts).lower() + " "
    hits = [(sum(said.count(w) for w in words), topic, advice) for topic, words, advice in _TOPICS]
    return [(t, a) for n, t, a in sorted(hits, key=lambda h: -h[0]) if n]


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


# What tapping each of the bot's buttons means, in plain words.
_TAPS = {
    "start:interested": "Tapped “Interested”",
    "start:webinar": "Asked for personal guidance",
    "edu:12": "Said they studied up to 12th or a diploma",
    "edu:grad": "Said they are a graduate or post-graduate",
    "edu:other": "Said they studied below 12th (not eligible)",
    "invest:yes": "Said YES, they can invest up to ₹5 lakh",
    "invest:no": "Said NO, they cannot invest up to ₹5 lakh",
    "franchise:yes": "Said yes to the franchise question",
    "franchise:no": "Said no to the franchise question",
    "docs:yes": "Said they have the documents",
    "docs:no": "Said they do not have the documents yet",
    "webinar:yes": "Said YES to personal guidance",
    "webinar:no": "Said they cannot make personal guidance then",
}
# What the bot is waiting for at each step, said simply.
_WAITING = {
    bot.CHOOSE_LANG: "choose a language",
    bot.AWAIT_PIN: "send their PIN code",
    bot.AWAIT_EDUCATION: "say how far they have studied",
    bot.AWAIT_FRANCHISE: "say whether they can invest up to ₹5 lakh",
    bot.AWAIT_INVEST: "say whether they can invest up to ₹5 lakh",
    bot.AWAIT_DOCS: "say whether they have the documents",
    bot.AWAIT_UPLOAD: "upload their documents",
    bot.AWAIT_WEBINAR: "say whether they can join personal guidance",
    bot.AWAIT_AVAILABILITY: "say when they can join personal guidance",
}
TIMELINE_LIMIT = 30


def _quote(text: str, n: int = 160) -> str:
    text = " ".join((text or "").split())
    return f"“{text[:n]}{'…' if len(text) > n else ''}”"


def timeline(db: Session, conv: WhatsAppConversation) -> List[dict]:
    """
    The conversation from the start, one plain line per thing that happened:
    when our campaign reached them, each button they tapped, what they wrote
    or asked (and whether the bot answered), and the documents.
    """
    data = conv.bot_data or {}
    coverage = data.get("coverage") or {}
    answered_ids = set(data.get("faq_answered") or [])
    lines: List[dict] = []
    reached = (db.query(WhatsAppCampaignRecipient, WhatsAppCampaign)
               .join(WhatsAppCampaign, WhatsAppCampaign.campaign_id == WhatsAppCampaignRecipient.campaign_id)
               .filter(WhatsAppCampaignRecipient.phone == conv.phone, WhatsAppCampaignRecipient.sent_at.isnot(None))
               .order_by(WhatsAppCampaignRecipient.sent_at).all())
    for r, c in reached:
        lines.append({"at": inbox.aware(r.sent_at), "kind": "event",
                      "text": f"Our campaign “{c.name}” reached them on WhatsApp"})

    for m in (db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == conv.phone)
              .order_by(WhatsAppMessage.created_at).all()):
        at = inbox.aware(m.created_at)
        payload = m.payload or {}
        if m.direction != "IN":
            # Only what a person on the team wrote; the bot's own messages are
            # the flow above, and a campaign is already a line of its own.
            if m.sent_by and "@" in m.sent_by:
                who = m.sent_by.split("@")[0].replace(".", " ").title()
                what = bot.message_text(m) or (f"sent {_media(m.kind)}" if m.kind in _MEDIA_WORDS else "")
                lines.append({"at": at, "kind": "team",
                              "text": f"{who} replied: {_quote(what)}" if m.kind == "text" else f"{who} {what}"})
            continue
        if m.kind == "interactive":
            tapped = payload.get("id") or ""
            if tapped.startswith("lang:"):
                code = tapped.split(":", 1)[1]
                lines.append({"at": at, "kind": "said", "text": f"Chose {LANGUAGE_NAMES.get(code, code)}"})
            else:
                lines.append({"at": at, "kind": "said", "text": _TAPS.get(tapped, f"Tapped “{m.body or tapped}”")})
            continue
        if m.kind == "button":
            lines.append({"at": at, "kind": "said", "text": f"Tapped “{m.body}” on our message"})
            continue
        if m.kind == "reaction":
            continue
        said = bot.message_text(m)
        if m.kind == "audio":
            if not said:
                lines.append({"at": at, "kind": "said", "text": "Sent a voice note (listen to it in the chat)"})
                continue
        elif m.kind != "text":
            words = _caption(m)
            last = lines[-1] if lines else None
            # A run of photos (or documents) sent one after another is one line.
            if last and last.get("media") == m.kind and not words and not last.get("words"):
                last["count"] += 1
                last["text"] = f"Sent {_media(m.kind, last['count'])}"
            else:
                text = f"Sent {_media(m.kind)}"
                if words:
                    text += f" ({words[:60]})" if m.kind in ("document", "location") else f" with the words {_quote(words, 100)}"
                lines.append({"at": at, "kind": "said", "text": text, "media": m.kind, "count": 1, "words": bool(words)})
            continue
        if not said:
            continue
        voice = " in a voice note" if m.kind == "audio" else ""
        pin = _PIN.search(said)
        faq = eko_knowledge.match(said)
        words = re.findall(r"\w+", said.lower())
        if faq or bot.looks_like_question(said):
            if faq and set(faq) <= answered_ids:
                lines.append({"at": at, "kind": "answered", "text": f"Asked{voice}: {_quote(said)}. The bot answered it."})
            elif faq:
                lines.append({"at": at, "kind": "waiting",
                              "text": f"Asked{voice}: {_quote(said)}. Needs your reply (a ready answer is below)."})
            else:
                lines.append({"at": at, "kind": "waiting", "text": f"Asked{voice}: {_quote(said)}. Needs your reply."})
        elif pin and len(words) <= 4:
            where = ""
            if coverage.get("pincode") == pin.group(0):
                where = " (we serve this area)" if applications._served(conv) else " (outside our area)"
            lines.append({"at": at, "kind": "said", "text": f"Sent their PIN code {pin.group(0)}{where}"})
        elif words and all(w in _ANSWER_WORDS for w in words):
            lines.append({"at": at, "kind": "said", "text": f"Replied {_quote(said, 40)}"})
        else:
            lines.append({"at": at, "kind": "said", "text": f"Wrote{voice}: {_quote(said)}"})

    if conv.upload_token and not conv.documents_submitted_at:
        docs = db.query(OnboardingDocument).filter(OnboardingDocument.phone == conv.phone).count()
        lines.append({"at": None, "kind": "event", "text": "Got the link to upload documents"
                      + (f"; {docs} uploaded so far" if docs else "; nothing uploaded yet")})
    if conv.documents_submitted_at:
        lines.append({"at": inbox.aware(conv.documents_submitted_at), "kind": "event",
                      "text": "Submitted their documents 🎉"})
    lines.sort(key=lambda x: (x["at"] is None, x["at"] or inbox.now()))
    for x in lines:
        x["when"] = _when(x["at"]) if x["at"] else ""
        for k in ("at", "media", "count", "words"):
            x.pop(k, None)
    return lines


def _direct_story(db: Session, conv: WhatsAppConversation) -> dict:
    """What someone who wrote to us directly sent, said and seems to want, and whether we answered."""
    msgs = (db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == conv.phone)
            .order_by(WhatsAppMessage.created_at).all())
    inbound = [m for m in msgs if m.direction == "IN" and m.kind != "reaction"]
    team = [m for m in msgs if m.direction != "IN" and m.sent_by and "@" in m.sent_by]
    texts = [t for t in ((bot.message_text(m) or (_caption(m) if m.kind not in ("text", "audio") else "")) for m in inbound) if t]
    media = {}
    for m in inbound:
        if m.kind not in ("text",) and not (m.kind == "audio" and bot.message_text(m)):
            media[m.kind] = media.get(m.kind, 0) + 1
    last_in = inbound[-1].created_at if inbound else None
    replied_after = bool(team and last_in and inbox.aware(team[-1].created_at) >= inbox.aware(last_in))
    return {"texts": texts, "media": media, "topics": topics(texts), "team": team, "replied": replied_after}


def in_short(conv: WhatsAppConversation, waiting_questions: int, direct: dict = None) -> str:
    """One or two plain sentences: where this person stands."""
    data = conv.bot_data or {}
    name = conv.profile_name or "This person"
    if direct is not None:
        parts = []
        sent = [_media(k, n) for k, n in direct["media"].items()]
        if sent:
            parts.append("sent " + (", ".join(sent[:-1]) + " and " + sent[-1] if len(sent) > 1 else sent[0]))
        if direct["texts"]:
            parts.append(f"wrote {_quote(direct['texts'][-1], 120)}"
                         + (f" (and {len(direct['texts']) - 1} more message{'s' if len(direct['texts']) > 2 else ''})"
                            if len(direct["texts"]) > 1 else ""))
        out = f"{name} wrote to us directly, not from an AutoGMap campaign"
        out += (": they " + " and ".join(parts) + ".") if parts else "."
        if direct["topics"]:
            out += f" It seems to be about {direct['topics'][0][0]}."
        elif direct["media"] and not direct["texts"]:
            out += " They did not say what they need."
        if direct["replied"]:
            out += f" The team replied on {_when(direct['team'][-1].created_at)}."
        else:
            out += " Nobody has replied yet." if not direct["team"] else " They wrote again after the team's last reply."
        return out
    q = applications.qualify(conv)
    if conv.documents_submitted_at:
        first = f"{name} has submitted their documents. This is a lead: the team should call them for the next steps."
    elif q["not_qualified"]:
        first = f"{name} is not eligible right now: {', '.join(q['not_qualified_reasons']).lower()}."
    elif conv.bot_step in (bot.WEBINAR_CONFIRMED, bot.WEBINAR_AVAILABILITY):
        first = f"{name} wants personal guidance" + (" and confirmed they can join." if conv.bot_step == bot.WEBINAR_CONFIRMED
                                                    else " and told us when they are free.") + " Someone should contact them."
    elif conv.bot_step in _WAITING:
        good = " and fits so far (area, education)" if q["pin_qualified"] and data.get("education") in ("12", "grad") else ""
        first = f"{name} is interested{good}. The bot is waiting for them to {_WAITING[conv.bot_step]}."
    elif not conv.bot_step:
        first = f"{name} wrote to us but has not started applying."
    else:
        first = f"{name}: {bot.STEP_LABELS.get(conv.bot_step, conv.bot_step).lower()}."
    if waiting_questions:
        first += f" {waiting_questions} question{'s are' if waiting_questions > 1 else ' is'} waiting for your reply."
    return first


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

    direct = _direct_story(db, conv) if is_direct(db, conv) else None
    step_text, key = STEP_NEXT.get(conv.bot_step, STEP_NEXT[None])
    if direct is not None:
        key = None
        if direct["topics"]:
            step_text = f"Reply to them about {direct['topics'][0][0]}. {direct['topics'][0][1]}"
        elif direct["media"] and not direct["texts"]:
            step_text = ("Open the chat to see what they sent, and ask them what they need. If they already run "
                         "a CSP and have a problem, pass it to the support team.")
        else:
            step_text = DIRECT_REPLY["action_none"]
        if direct["replied"]:
            step_text = "The team has replied; wait for them to write back. " + step_text
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
    if direct is not None and not reply:
        # A polite holding reply in Hinglish, the way most people write to us.
        first = (conv.profile_name or "").split(" ")[0]
        reply = (f"Namaste{' ' + first if first else ''} ji, aapka message mil gaya hai. "
                 + ("Kripya bataiye hum aapki kya madad kar sakte hain?" if not direct["texts"]
                    else "Hamari team jald hi aapki madad karegi."))
        lang = "Hinglish"

    # Waiting for a person: no ready answer, or one the bot did not send.
    needing = [q for q in questions if not q["answered_by_bot"]]
    events = timeline(db, conv)
    earlier = max(len(events) - TIMELINE_LIMIT, 0)
    headline = conv.bot_step and bot.STEP_LABELS.get(conv.bot_step, conv.bot_step) or (
        "Wrote to us directly" if direct is not None else "Has not started")
    if conv.needs_attention:
        headline += " · needs attention"
    from src.services import tickets
    ticket = tickets.open_ticket(db, conv.phone) if conv.needs_attention else None
    return {
        "generated_at": inbox.now().isoformat(),
        "ticket_id": ticket.ticket_id if ticket else None,
        "person": _person(db, conv),
        "headline": headline,
        "in_short": in_short(conv, len(needing), direct),
        "direct": direct is not None,
        "timeline": events[-TIMELINE_LIMIT:],
        "timeline_earlier": earlier,
        "waiting_questions": [{"text": q["text"], "at": q["at"], "voice": q["voice"]} for q in needing][-6:],
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
    lines += ["", "IN SHORT", s["in_short"]]
    if s.get("attention"):
        lines.append(f"Why it needs attention: {s['attention']['reason'] or 'marked for the team'} ({s['attention']['at']})")
    lines += ["", "THE CONVERSATION SO FAR"]
    if s.get("timeline_earlier"):
        lines.append(f"  (… {s['timeline_earlier']} earlier steps)")
    marks = {"waiting": "❗ ", "answered": "✓ "}
    lines += [f"- {t['when'] + ' · ' if t['when'] else ''}{marks.get(t['kind'], '')}{t['text']}" for t in s["timeline"]]
    if s["waiting_questions"]:
        lines += ["", "QUESTIONS WAITING FOR YOUR REPLY"]
        lines += [f"- “{q['text']}”" for q in s["waiting_questions"]]
    answers = [(q, a) for q in s["questions"] if not q["answered_by_bot"] for a in q["answers"]]
    if answers:
        lines += ["", "ANSWERS YOU CAN SEND (from Eko's FAQ)"]
        lines += [f"- To “{q['text']}”: {a['answer']}" for q, a in answers]
    lines += ["", "WHAT TO DO NEXT", f"- {s['next']['action']}"]
    if s["next"]["reply"]:
        lines += [f"- A reply you could send ({s['next']['reply_language']}):", "", s["next"]["reply"]]
    return "\n".join(lines)
