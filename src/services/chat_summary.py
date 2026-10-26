"""
A conversation at a glance, for whoever opens it in the inbox and for the
email sent when it needs attention: who the person is and where, how far
they got, what they asked (with the answers Eko's FAQ has for it), what else
they wrote, and what to send them next, ready to copy in their language.

Written in Hinglish for the team (the user, 2026-10-23); the ready reply to
the person stays in their own language.

Built from the conversation itself, not by a language model, so nobody's
messages leave our server and the summary says only what happened.
"""
import re
from datetime import timedelta, timezone
from typing import List

from sqlalchemy.orm import Session

from src.models import Business
from src.models.inbox import ChatActivity, OnboardingDocument, WhatsAppConversation, WhatsAppMessage
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
    None: ("Inhone abhi shuru nahi kiya hai. Greet kijiye aur Interested tap karne ko kahiye.", "greeting"),
    bot.CHOOSE_LANG: ("Language choose karne ka wait hai. Unse ek language chunne ko kahiye.", "language_prompt"),
    bot.AWAIT_PIN: ("PIN code ka wait hai. Unka 6-digit PIN code maangiye.", "ask_pin"),
    bot.AWAIT_EDUCATION: ("Education ka wait hai. Poochiye kitna padhe hain.", "ask_education"),
    bot.AWAIT_FRANCHISE: ("Investment ke jawab ka wait hai. ₹3–5 lakh kis cheez ke liye hai samjhaiye, phir poochiye.", "ask_invest"),
    bot.AWAIT_INVEST: ("Investment ke jawab ka wait hai. ₹3–5 lakh kis cheez ke liye hai (devices, e-wallet, "
                       "setup) samjhaiye aur poochiye ki kya woh invest kar sakte hain.", "ask_invest"),
    bot.AWAIT_DOCS: ("Documents hain ya nahi, iska wait hai. Unke saath documents ki list dekhiye.", "ask_docs"),
    bot.AWAIT_UPLOAD: ("Upload link mil gaya hai par submit nahi kiya. Yaad dilaiye, aur scan ya upload karne mein "
                       "madad offer kijiye.", None),
    bot.SUBMITTED: ("Documents submit ho gaye: yeh lead hai. Thank you boliye aur aage ke steps ke liye team ki call "
                    "arrange kijiye.", None),
    bot.NOT_SERVED: ("Inka PIN hamare area se bahar hai. Unhe bataiye, aur PIN note kar lijiye agar hum wahan "
                     "expand karein.", None),
    bot.NOT_ELIGIBLE: ("12th se kam padhe hain, isliye Banking Outlet ke liye eligible nahi. Politely thank you "
                       "boliye.", None),
    bot.NOT_INVESTING: ("Inhone kaha invest nahi kar sakte. Samjhaiye ki paise ka ek hissa unke e-wallet mein unka hi "
                        "rehta hai, aur poochiye kya ₹3–5 lakh ho sakta hai.", "invest_explained"),
    bot.HANDOVER: ("Teen baar galat PIN code ke baad bot ne inhe team ko diya. Call kijiye ya PIN dobara maangiye.", "ask_pin"),
    bot.GUIDANCE_QA: ("Personal guidance maangi hai: bot inke sawaalon ke jawab de raha hai. Jo sawaal aapke liye "
                      "chhode hain unka jawab dijiye, aur jab ready hon to Interested tap karne ko kahiye.", None),
    bot.AWAIT_WEBINAR: ("Personal guidance ke baare mein poocha. Poochiye kya woh join kar sakte hain.", None),
    bot.AWAIT_AVAILABILITY: ("Personal guidance kab join kar sakte hain, iska wait hai. Din aur time poochiye.", None),
    bot.WEBINAR_CONFIRMED: ("Personal guidance confirm hai. Time ke saath unse contact kijiye.", None),
    bot.WEBINAR_AVAILABILITY: ("Personal guidance ke liye apna time bata diya hai. Usi time contact kijiye.", None),
}
# The bot's steps as the summary names them, in Hinglish.
STEP_HINGLISH = {
    bot.CHOOSE_LANG: "Language chun rahe hain",
    bot.AWAIT_PIN: "PIN code ka wait",
    bot.AWAIT_EDUCATION: "Education poochi gayi",
    bot.AWAIT_FRANCHISE: "Franchise ke baare mein poocha",
    bot.NOT_ELIGIBLE: "12th se kam — eligible nahi",
    bot.AWAIT_INVEST: "Investment ke baare mein poocha",
    bot.AWAIT_DOCS: "Documents ke baare mein poocha",
    bot.AWAIT_UPLOAD: "Upload link bheja gaya",
    bot.SUBMITTED: "Documents submit ho gaye",
    bot.NOT_SERVED: "Hamare area se bahar",
    bot.NOT_INVESTING: "Invest nahi kar sakte",
    bot.HANDOVER: "Team ki zaroorat hai",
    bot.AWAIT_WEBINAR: "Personal guidance ke baare mein poocha",
    bot.AWAIT_AVAILABILITY: "Guidance ka time poocha",
    bot.WEBINAR_CONFIRMED: "Personal guidance confirm",
    bot.WEBINAR_AVAILABILITY: "Guidance ka time bata diya",
    bot.GUIDANCE_QA: "Personal guidance: sawaal pooch rahe hain",
}


# What someone writing to us directly (not from a campaign) is most likely
# about, from the words they use: (topic, what the team should do).
_TOPICS = [
    ("device install ya setup karna", ("install", "istall", "instal", "device", "machine", "biometric",
                                           "fingerprint", "finger", "scanner", "printer", "setup", "set up", "मशीन",
                                           "डिवाइस", "इंस्टॉल"),
     "Agar woh pehle se CSP chalate hain, to device ya installation ke liye support team ko bhejiye."),
    ("ATM ya card", ("atm", "card", "debit", "kard", "एटीएम", "कार्ड"),
     "Unki CSP ID maangiye aur support team ko bhejiye."),
    ("paisa, payment ya transaction or a transaction", ("commission", "payment", "paisa", "paise", "settlement", "wallet",
                                            "balance", "refund", "transaction", "txn", "credit", "debited", "amount",
                                            "पैसा", "पैसे", "कमीशन", "भुगतान"),
     "Unki CSP ID aur transaction details maangiye, aur support ya accounts team ko bhejiye."),
    ("login ya unki ID", ("login", "log in", "password", "otp", "user id", "userid", "blocked", "block",
                                "लॉगिन", "पासवर्ड"),
     "Unki CSP ID maangiye aur support team ko bhejiye."),
    ("CSP agreement, certificate ya papers", ("agreement", "certificate", "renew", "valid", "expire", "iibf",
                                                   "एग्रीमेंट", "सर्टिफिकेट"),
     "Dekhiye unhe papers ke baare mein kya chahiye, aur support team ko bhejiye."),
    # "CSP" alone is mostly someone who already runs one, so it is not a sign here.
    ("CSP banna (banking outlet kholna)", ("kiosk kholna", "kiosk chahiye", "csp chahiye", "csp banna",
                                                  "franchise", "apply", "join", "mini bank", "mini branch",
                                                  "banking point", "कियोस्क खोलना", "फ्रेंचाइज़ी", "जुड़ना", "ખોલવું"),
     "Shayad banking outlet kholna chahte hain: greeting bhejiye taaki bot unhe aage le jaaye."),
]
# Hinglish counts the same word for one and many: "1 photo", "2 photo".
_MEDIA_WORDS = {"image": "photo", "document": "document", "video": "video", "sticker": "sticker",
                "location": "location", "contacts": "contact card", "audio": "voice note",
                "unsupported": "message jo WhatsApp ne aage nahi bheja (poll, view-once ya edit kiya hua)"}
DIRECT_REPLY = {
    "action_none": "Unhone jo bheja hai padhiye aur reply kijiye. Woh onboarding flow mein nahi hain; agar pehle se "
                   "CSP chalate hain aur koi problem hai, to support team ko bhejiye.",
}


def _media(kind: str, n: int = 1) -> str:
    return f"{n} {_MEDIA_WORDS.get(kind, 'message jo inbox dikha nahi sakta')}"


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
        out.append(f"Campaign “{c.name}” {_when(r.sent_at)} ko pahuncha"
                   + (f" (kul {len(reached)} campaigns)" if len(reached) > 1 else "") + ".")
    if data.get("trigger"):
        out.append(f"“{data['trigger']}” tap kiya.")
    if data.get("lang"):
        out.append(f"{LANGUAGE_NAMES.get(data['lang'], data['lang'])} chuni.")
    coverage = data.get("coverage") or {}
    if coverage.get("pincode"):
        served = applications._served(conv)
        out.append(f"PIN {coverage['pincode']} diya: " + ("hamare area mein" if served else "hamare area se bahar")
                   + (f" (hamara sabse paas {coverage['nearest_pincode']}, {coverage.get('distance_km')} km)"
                      if coverage.get("nearest_pincode") and coverage.get("nearest_pincode") != coverage["pincode"]
                      else "") + ".")
    edu = data.get("education")
    if edu:
        out.append({"12": "12th/Diploma tak padhe hain.", "grad": "Graduate ya post-graduate hain.",
                    "other": "12th se kam: eligible nahi."}.get(edu, f"Education: {edu}."))
    if data.get("can_invest") is not None:
        out.append("₹3–5 lakh invest kar sakte hain." if data["can_invest"] else "Kaha ₹3–5 lakh invest nahi kar sakte.")
    docs = db.query(OnboardingDocument).filter(OnboardingDocument.phone == conv.phone).count()
    if conv.documents_submitted_at:
        out.append(f"{_when(conv.documents_submitted_at)} ko {docs} documents submit kiye: yeh lead hai.")
    elif conv.upload_token:
        out.append("Upload link bheja gaya" + (f"; ab tak {docs} documents upload hue" if docs else "; abhi kuch upload nahi hua") + ".")
    guidance = data.get("webinar") or {}
    if guidance.get("answer") == "yes":
        out.append("Personal guidance confirm kiya.")
    elif guidance.get("availability"):
        out.append(f"Personal guidance ke liye free hain: {guidance['availability']}.")
    if data.get("faq_answered"):
        out.append("Bot ne FAQ se jawab diye: " + ", ".join(sorted(set(data["faq_answered"]))) + ".")
    return out


# What tapping each of the bot's buttons means, in plain words.
_TAPS = {
    "start:interested": "“Interested” tap kiya",
    "start:webinar": "Personal guidance maangi",
    "edu:12": "Bataya 12th ya diploma tak padhe hain",
    "edu:grad": "Bataya graduate ya post-graduate hain",
    "edu:other": "Bataya 12th se kam padhe hain (eligible nahi)",
    "invest:yes": "HAAN kaha, ₹3–5 lakh invest kar sakte hain",
    "invest:no": "NAHI kaha, ₹3–5 lakh invest nahi kar sakte",
    "franchise:yes": "Franchise wale sawaal par haan kaha",
    "franchise:no": "Franchise wale sawaal par nahi kaha",
    "docs:yes": "Bataya documents hain",
    "docs:no": "Bataya abhi documents nahi hain",
    "webinar:yes": "Personal guidance ke liye HAAN kaha",
    "webinar:no": "Kaha us time personal guidance join nahi kar sakte",
}
# What the bot is waiting for at each step, said simply: "bot ... ka wait kar raha hai".
_WAITING = {
    bot.CHOOSE_LANG: "language chunne",
    bot.AWAIT_PIN: "PIN code bhejne",
    bot.AWAIT_EDUCATION: "education batane",
    bot.AWAIT_FRANCHISE: "₹3–5 lakh invest kar sakte hain ya nahi, yeh batane",
    bot.AWAIT_INVEST: "₹3–5 lakh invest kar sakte hain ya nahi, yeh batane",
    bot.AWAIT_DOCS: "documents hain ya nahi, yeh batane",
    bot.AWAIT_UPLOAD: "documents upload karne",
    bot.GUIDANCE_QA: "sawaal poochne, ya shuru karne ke liye Interested tap karne",
    bot.AWAIT_WEBINAR: "personal guidance join kar sakte hain ya nahi, yeh batane",
    bot.AWAIT_AVAILABILITY: "personal guidance kab join kar sakte hain, yeh batane",
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
                      "text": f"Hamara campaign “{c.name}” WhatsApp par pahuncha"})

    for m in (db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == conv.phone)
              .order_by(WhatsAppMessage.created_at).all()):
        at = inbox.aware(m.created_at)
        payload = m.payload or {}
        if m.direction != "IN":
            # Only what a person on the team wrote; the bot's own messages are
            # the flow above, and a campaign is already a line of its own.
            if m.sent_by and "@" in m.sent_by:
                who = m.sent_by.split("@")[0].replace(".", " ").title()
                what = bot.message_text(m) or (f"ne {_media(m.kind)} bheja" if m.kind in _MEDIA_WORDS else "")
                lines.append({"at": at, "kind": "team",
                              "text": f"{who} ne reply kiya: {_quote(what)}" if m.kind == "text" else f"{who} {what}"})
            continue
        if m.kind == "interactive":
            tapped = payload.get("id") or ""
            if tapped.startswith("lang:"):
                code = tapped.split(":", 1)[1]
                lines.append({"at": at, "kind": "said", "text": f"{LANGUAGE_NAMES.get(code, code)} chuni"})
            else:
                lines.append({"at": at, "kind": "said", "text": _TAPS.get(tapped, f"“{m.body or tapped}” tap kiya")})
            continue
        if m.kind == "button":
            lines.append({"at": at, "kind": "said", "text": f"Hamare message par “{m.body}” tap kiya"})
            continue
        if m.kind == "reaction":
            continue
        said = bot.message_text(m)
        if m.kind == "audio":
            if not said:
                lines.append({"at": at, "kind": "said", "text": "Voice note bheja (chat mein sun lijiye)"})
                continue
        elif m.kind != "text":
            words = _caption(m)
            last = lines[-1] if lines else None
            # A run of photos (or documents) sent one after another is one line.
            if last and last.get("media") == m.kind and not words and not last.get("words"):
                last["count"] += 1
                last["text"] = f"{_media(m.kind, last['count'])} bheje"
            else:
                text = f"{_media(m.kind)} bheja"
                if words:
                    text += f" ({words[:60]})" if m.kind in ("document", "location") else f", saath mein likha {_quote(words, 100)}"
                lines.append({"at": at, "kind": "said", "text": text, "media": m.kind, "count": 1, "words": bool(words)})
            continue
        if not said:
            continue
        voice = " (voice note mein)" if m.kind == "audio" else ""
        pin = _PIN.search(said)
        faq = eko_knowledge.match(said)
        words = re.findall(r"\w+", said.lower())
        if faq or bot.looks_like_question(said):
            if faq and set(faq) <= answered_ids:
                lines.append({"at": at, "kind": "answered", "text": f"Poocha{voice}: {_quote(said)}. Bot ne jawab de diya."})
            elif faq:
                lines.append({"at": at, "kind": "waiting",
                              "text": f"Poocha{voice}: {_quote(said)}. Aapke reply ka wait hai (ready jawab neeche hai)."})
            else:
                lines.append({"at": at, "kind": "waiting", "text": f"Poocha{voice}: {_quote(said)}. Aapke reply ka wait hai."})
        elif pin and len(words) <= 4:
            where = ""
            if coverage.get("pincode") == pin.group(0):
                where = " (hamara area hai)" if applications._served(conv) else " (hamare area se bahar)"
            lines.append({"at": at, "kind": "said", "text": f"PIN code {pin.group(0)} bheja{where}"})
        elif words and all(w in _ANSWER_WORDS for w in words):
            lines.append({"at": at, "kind": "said", "text": f"Reply kiya {_quote(said, 40)}"})
        else:
            lines.append({"at": at, "kind": "said", "text": f"Likha{voice}: {_quote(said)}"})

    # Handovers between the bot and the team, and the dispositions recorded.
    from src.services import handover
    for a in db.query(ChatActivity).filter(ChatActivity.phone == conv.phone).all():
        name = handover.who(a.by)
        text = {"to_person": f"{name} ne bot se chat le li",
                "to_bot": f"{name} ne chat wapas bot ko di"
                          + (f" ({handover.label(a.value)})" if a.value else ""),
                "disposition": f"{name} ne outcome record kiya: {handover.label(a.value) or a.value}",
                "stage": f"Lead {a.value} par pahunchi"}.get(a.kind, a.kind)
        if a.note and a.kind != "to_bot":
            text += f" — {_quote(a.note, 100)}"
        lines.append({"at": inbox.aware(a.at), "kind": "team", "text": text})

    if conv.upload_token and not conv.documents_submitted_at:
        docs = db.query(OnboardingDocument).filter(OnboardingDocument.phone == conv.phone).count()
        lines.append({"at": None, "kind": "event", "text": "Documents upload karne ka link mila"
                      + (f"; ab tak {docs} upload hue" if docs else "; abhi kuch upload nahi hua")})
    if conv.documents_submitted_at:
        lines.append({"at": inbox.aware(conv.documents_submitted_at), "kind": "event",
                      "text": "Documents submit kar diye 🎉"})
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
    name = conv.profile_name or "Inhone"
    if direct is not None:
        parts = []
        sent = [_media(k, n) for k, n in direct["media"].items()]
        if sent:
            parts.append((", ".join(sent[:-1]) + " aur " + sent[-1] if len(sent) > 1 else sent[0]) + " bheja")
        if direct["texts"]:
            parts.append(f"likha {_quote(direct['texts'][-1], 120)}"
                         + (f" (aur {len(direct['texts']) - 1} message)" if len(direct["texts"]) > 1 else ""))
        out = f"{name} ne seedha humein likha, AutoGMap campaign se nahi"
        out += (": " + " aur ".join(parts) + ".") if parts else "."
        if direct["topics"]:
            out += f" Lagta hai baat {direct['topics'][0][0]} ke baare mein hai."
        elif direct["media"] and not direct["texts"]:
            out += " Unhone nahi bataya ki kya chahiye."
        if direct["replied"]:
            out += f" Team ne {_when(direct['team'][-1].created_at)} ko reply kiya."
        else:
            out += " Abhi tak kisi ne reply nahi kiya." if not direct["team"] else " Team ke last reply ke baad unhone phir likha."
        return out
    q = applications.qualify(conv)
    if conv.documents_submitted_at:
        first = f"{name} ne documents submit kar diye hain. Yeh lead hai: aage ke steps ke liye team inhe call kare."
    elif q["not_qualified"] and not (q["other_proposal"] and conv.bot_step in _WAITING):
        first = f"{name} abhi eligible nahi hain: {', '.join(q['not_qualified_reasons']).lower()}."
    elif q["other_proposal"]:
        first = (f"{name} interested hain, par PIN hamare SBI branch area se bahar hai: SBI branch code ke liye "
                 f"qualified nahi, doosre proposal (BT, HDFC...) ke liye rakhe gaye hain. Bot unke "
                 f"{_WAITING[conv.bot_step]} ka wait kar raha hai.")
    elif conv.bot_step in (bot.WEBINAR_CONFIRMED, bot.WEBINAR_AVAILABILITY):
        first = f"{name} ko personal guidance chahiye" + (" aur join karna confirm kiya hai." if conv.bot_step == bot.WEBINAR_CONFIRMED
                                                         else " aur bataya hai kab free hain.") + " Koi inse contact kare."
    elif conv.bot_step in _WAITING:
        good = " aur ab tak fit hain (area, education)" if q["pin_qualified"] and data.get("education") in ("12", "grad") else ""
        first = f"{name} interested hain{good}. Bot unke {_WAITING[conv.bot_step]} ka wait kar raha hai."
    elif not conv.bot_step:
        first = f"{name} ne humein likha par abhi apply karna shuru nahi kiya."
    else:
        first = f"{name}: {STEP_HINGLISH.get(conv.bot_step, conv.bot_step)}."
    if waiting_questions:
        first += f" {waiting_questions} sawaal aapke reply ka wait kar rahe hain."
    return first


def _ready_replies_on(db: Session) -> bool:
    from src.services import agent_controls
    return agent_controls.is_on(db, "inbox_ready_reply")


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
            other.append({"text": "(voice note, text nahi bana: chat mein sun lijiye)", "at": _when(m.created_at), "voice": True})
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
            step_text = f"Inhe {direct['topics'][0][0]} ke baare mein reply kijiye. {direct['topics'][0][1]}"
        elif direct["media"] and not direct["texts"]:
            step_text = ("Chat kholkar dekhiye kya bheja hai, aur poochiye kya chahiye. Agar pehle se CSP chalate hain "
                         "aur koi problem hai, to support team ko bhejiye.")
        else:
            step_text = DIRECT_REPLY["action_none"]
        if direct["replied"]:
            step_text = "Team ne reply kar diya hai; unke jawab ka wait kijiye. " + step_text
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
    headline = conv.bot_step and STEP_HINGLISH.get(conv.bot_step, conv.bot_step) or (
        "Seedha humein likha" if direct is not None else "Abhi shuru nahi kiya")
    if conv.needs_attention:
        headline += " · dhyan dena hai"
    from src.services import handover, tickets
    ticket = tickets.open_ticket(db, conv.phone) if conv.needs_attention else None
    short = in_short(conv, len(needing), direct)
    if conv.bot_paused and conv.handled_by:
        short += (f" {_when(conv.handled_since)} se {handover.who(conv.handled_by)} yeh chat dekh rahe hain; "
                  "jab tak chat wapas nahi milti, bot chup rahega.")
        step_text = ("Kaam ho jaaye to outcome record kijiye aur chat wapas bot ko dijiye; bot wahin se dobara "
                     "poochega jahan ruka tha. " + step_text)
    disposition = handover.current(conv)
    return {
        "generated_at": inbox.now().isoformat(),
        "ticket_id": ticket.ticket_id if ticket else None,
        "person": _person(db, conv),
        "headline": headline,
        "in_short": short,
        "disposition": disposition,
        "handled_by": conv.handled_by if conv.bot_paused else None,
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
            "action": step_text if open_window else step_text + " 24 ghante ki window band hai: ab sirf campaign template se hi pahunch sakte hain.",
            # The admin can turn ready replies off (agent_controls).
            "reply": reply if open_window and _ready_replies_on(db) else None,
            "reply_language": LANGUAGE_NAMES.get(lang, lang),
            "window_open": open_window,
        },
    }


def as_text(s: dict) -> str:
    """The summary as plain text, for the attention email."""
    p = s["person"]
    place = ", ".join(x for x in (p["tehsil"], p["district"], p["state"]) if x)
    lines = ([f"Ticket:    {s['ticket_id']} (raise hua)", ""] if s.get("ticket_id") else []) + [
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
    lines += ["", "SHORT MEIN", s["in_short"]]
    if s.get("attention"):
        lines.append(f"Dhyan kyun dena hai: {s['attention']['reason'] or 'team ke liye mark kiya gaya'} ({s['attention']['at']})")
    lines += ["", "AB TAK KI BAATCHEET"]
    if s.get("timeline_earlier"):
        lines.append(f"  (… {s['timeline_earlier']} pehle ke steps)")
    marks = {"waiting": "❗ ", "answered": "✓ "}
    lines += [f"- {t['when'] + ' · ' if t['when'] else ''}{marks.get(t['kind'], '')}{t['text']}" for t in s["timeline"]]
    if s["waiting_questions"]:
        lines += ["", "SAWAAL JO AAPKE REPLY KA WAIT KAR RAHE HAIN"]
        lines += [f"- “{q['text']}”" for q in s["waiting_questions"]]
    answers = [(q, a) for q in s["questions"] if not q["answered_by_bot"] for a in q["answers"]]
    if answers:
        lines += ["", "JAWAB JO AAP BHEJ SAKTE HAIN (Eko ke FAQ se)"]
        lines += [f"- “{q['text']}” ke liye: {a['answer']}" for q, a in answers]
    lines += ["", "AAGE KYA KAREIN", f"- {s['next']['action']}"]
    if s["next"]["reply"]:
        lines += [f"- Yeh reply bhej sakte hain ({s['next']['reply_language']}):", "", s["next"]["reply"]]
    return "\n".join(lines)
