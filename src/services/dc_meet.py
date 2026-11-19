"""
"Meet the District Coordinator", the second button on CSPs near DCs campaigns (Mansi, 19 Nov 2026),
in place of Personal Guidance.

A tap: the bot names their nearest District Coordinator and asks which day they are free, so
the DC can visit them and explain Eko and how to open an SBI CSP with Eko. Their answer goes to
Biswajit Sir (followups.DC_VISIT_NOTIFY) by email, with who they are, their shop and place, the
chat so far and the DCs near them; a ticket opens, and they are thanked. The disposition is
"Wants a DC visit".

The nearest DC comes from dc_network (the team's DC list), by the district of the shop the
campaign reached, else of their PIN. With no DC listed there, they are still asked their day
and Biswajit Sir arranges it.
"""
import logging
import threading
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger("gmap_scraper.dc_meet")

ASK = {
    "en": "Thank you for your interest 🙏 Your nearest District Coordinator is {dc}{where}. Please tell us which day you are available: our DC will visit you that day and explain Eko and how you can open an SBI Customer Service Point with Eko.",
    "hi": "आपकी रुचि के लिए धन्यवाद 🙏 आपके नज़दीकी डिस्ट्रिक्ट कोऑर्डिनेटर {dc}{where} हैं। कृपया बताइए आप किस दिन उपलब्ध हैं: हमारे DC उसी दिन आपके यहाँ आकर आपको Eko के बारे में और Eko के साथ आप SBI का CSP कैसे खोल सकते हैं, सब बताएँगे।",
    "hinglish": "Aapki ruchi ke liye dhanyavaad 🙏 Aapke nazdeeki District Coordinator {dc}{where} hain. Kripya bataiye aap kis din available hain: hamare DC usi din aapke yahan aakar aapko Eko ke baare mein aur Eko ke saath aap SBI ka CSP kaise khol sakte hain, sab batayenge.",
    "pa": "ਤੁਹਾਡੀ ਦਿਲਚਸਪੀ ਲਈ ਧੰਨਵਾਦ 🙏 ਤੁਹਾਡੇ ਨੇੜਲੇ ਡਿਸਟ੍ਰਿਕਟ ਕੋਆਰਡੀਨੇਟਰ {dc}{where} ਹਨ। ਕਿਰਪਾ ਕਰਕੇ ਦੱਸੋ ਤੁਸੀਂ ਕਿਸ ਦਿਨ ਉਪਲਬਧ ਹੋ: ਸਾਡੇ DC ਉਸੇ ਦਿਨ ਤੁਹਾਡੇ ਕੋਲ ਆ ਕੇ ਤੁਹਾਨੂੰ Eko ਬਾਰੇ ਅਤੇ Eko ਨਾਲ ਤੁਸੀਂ SBI ਦਾ CSP ਕਿਵੇਂ ਖੋਲ੍ਹ ਸਕਦੇ ਹੋ, ਸਭ ਦੱਸਣਗੇ।",
    "gu": "તમારી રુચિ માટે આભાર 🙏 તમારા નજીકના ડિસ્ટ્રિક્ટ કોઓર્ડિનેટર {dc}{where} છે. કૃપા કરીને જણાવો તમે કયા દિવસે ઉપલબ્ધ છો: અમારા DC એ જ દિવસે તમારે ત્યાં આવીને તમને Eko વિશે અને Eko સાથે તમે SBI નું CSP કેવી રીતે ખોલી શકો, બધું સમજાવશે.",
}
ASK_NO_NAME = {
    "en": "our District Coordinator for your area", "hi": "आपके क्षेत्र के हमारे डिस्ट्रिक्ट कोऑर्डिनेटर",
    "hinglish": "aapke area ke hamare District Coordinator", "pa": "ਤੁਹਾਡੇ ਇਲਾਕੇ ਦੇ ਸਾਡੇ ਡਿਸਟ੍ਰਿਕਟ ਕੋਆਰਡੀਨੇਟਰ",
    "gu": "તમારા વિસ્તારના અમારા ડિસ્ટ્રિક્ટ કોઓર્ડિનેટર",
}
THANKS = {
    "en": "Thank you 🙏 Our District Coordinator will visit you as per your availability. Have a wonderful day!",
    "hi": "धन्यवाद 🙏 आपकी उपलब्धता के हिसाब से हमारे डिस्ट्रिक्ट कोऑर्डिनेटर आपके यहाँ आएँगे। आपका दिन मंगलमय हो!",
    "hinglish": "Dhanyavaad 🙏 Aapki availability ke hisaab se hamare District Coordinator aapke yahan visit karenge. Aapka din mangalmay ho!",
    "pa": "ਧੰਨਵਾਦ 🙏 ਤੁਹਾਡੀ ਉਪਲਬਧਤਾ ਅਨੁਸਾਰ ਸਾਡੇ ਡਿਸਟ੍ਰਿਕਟ ਕੋਆਰਡੀਨੇਟਰ ਤੁਹਾਡੇ ਕੋਲ ਆਉਣਗੇ। ਤੁਹਾਡਾ ਦਿਨ ਸ਼ੁਭ ਹੋਵੇ!",
    "gu": "આભાર 🙏 તમારી અનુકૂળતા પ્રમાણે અમારા ડિસ્ટ્રિક્ટ કોઓર્ડિનેટર તમારે ત્યાં આવશે. તમારો દિવસ શુભ રહે!",
}


def _variant(db: Session, conv) -> str:
    from src.services import onboarding_bot as bot
    lang = bot._lang(db, conv)
    if lang == "hi" and (conv.bot_data or {}).get("script") == "latin":
        return "hinglish"
    return lang if lang in ASK else ("hi" if lang == "mr" else "en")


def _their_place(db: Session, conv) -> tuple:
    """(district, state): the shop the campaign reached, else their PIN's."""
    from src.models import Business
    from src.models.whatsapp import WhatsAppCampaignRecipient
    from src.services import dc_visit
    r = (db.query(WhatsAppCampaignRecipient).filter(WhatsAppCampaignRecipient.phone == conv.phone,
                                                     WhatsAppCampaignRecipient.business_id.isnot(None))
         .order_by(WhatsAppCampaignRecipient.created_at.desc()).first())
    biz = db.get(Business, r.business_id) if r is not None else None
    if biz is not None and biz.district:
        return biz.district, biz.state
    return dc_visit.place_of(db, conv)


def nearby_dcs(db: Session, conv) -> List[dict]:
    """The DC of their district first, then the other DCs in their state."""
    from src.services import dc_network
    rows = dc_network.load(db)
    district, state = _their_place(db, conv)
    mine = dc_network.dc_for(db, district, state, rows)
    same_state = [r for r in rows if r is not mine and state and dc_network._key(r.get("state")) == dc_network._key(state)]
    return ([mine] if mine else []) + same_state[:5]


def start(db: Session, conv) -> None:
    """The button was tapped: their nearest DC, and which day they are free."""
    from src.services import onboarding_bot as bot
    dcs = nearby_dcs(db, conv)
    district, _state = _their_place(db, conv)
    v = _variant(db, conv)
    name = (dcs[0].get("dc") if dcs and dcs[0].get("dc") else None) or ASK_NO_NAME[v]
    where = f" ({district})" if district else ""
    bot._move(conv, bot.AWAIT_DC_DAY)
    conv.bot_data = {**(conv.bot_data or {}), "dc_meet": {"dc": dcs[0] if dcs else None, "district": district}}
    flag_modified(conv, "bot_data")
    bot._say(db, conv, ASK[v].format(dc=name, where=where))


def got_day(db: Session, conv, said: str) -> None:
    """Their answer: thanked, a ticket, and an email to Biswajit Sir with everything he needs."""
    from src.services import handover, tickets
    from src.services import onboarding_bot as bot
    held = dict((conv.bot_data or {}).get("dc_meet") or {})
    held["availability"] = (said or "").strip()[:300]
    conv.bot_data = {**(conv.bot_data or {}), "dc_meet": held}
    flag_modified(conv, "bot_data")
    bot._move(conv, bot.DC_BOOKED)
    handover.record(db, conv, "int_dc_visit", "bot", note=f"Available: {held['availability']}", tell=False)
    bot.flag(conv, f"Wants the District Coordinator's visit. Available: {held['availability']}")
    tickets.raise_or_update(db, conv)
    bot._say(db, conv, THANKS[_variant(db, conv)])
    db.flush()
    subject, body = email(db, conv)
    threading.Thread(target=_send, args=(subject, body), daemon=True).start()


def email(db: Session, conv) -> tuple:
    from src.services import chat_summary
    held = (conv.bot_data or {}).get("dc_meet") or {}
    district, state = _their_place(db, conv)
    cov = (conv.bot_data or {}).get("coverage") or {}
    src = _source(db, conv)
    lines = [
        f"{conv.profile_name or 'A candidate'} wants our District Coordinator to visit them.",
        "",
        f"Available    {held.get('availability') or '-'}",
        f"Name         {conv.profile_name or '-'}",
        f"Phone        {conv.phone}",
        f"Shop         {src or '-'}",
        f"Place        {', '.join(x for x in (district, state) if x) or '-'}" + (f" (PIN {cov['pincode']})" if cov.get("pincode") else ""),
        "",
        "Nearest District Coordinators:",
    ]
    dcs = nearby_dcs(db, conv)
    lines += [f"  - {d.get('dc') or 'DC'}, {d.get('district')}, {d.get('state') or ''}" + (f", {d['phone']}" if d.get("phone") else "")
              for d in dcs] or ["  (no DC listed for this place yet)"]
    try:
        lines += ["", "The chat so far:", chat_summary.as_text(chat_summary.summarise(db, conv))]
    except Exception:
        logger.exception("dc_meet event=SUMMARY_FAILED")
    return f"AutoGMap: DC visit wanted — {conv.profile_name or conv.phone}, available {held.get('availability') or '-'}", "\n".join(lines)


def _source(db: Session, conv) -> Optional[str]:
    from src.services import applications
    s = applications._sources(db, [conv.phone]).get(conv.phone) or {}
    return " · ".join(x for x in (s.get("business_name"), s.get("category")) if x) or None


def _send(subject: str, body: str) -> None:
    from src.services import followups, notifier
    try:
        notifier._send(followups.DC_VISIT_NOTIFY, subject, body)
    except Exception:
        logger.exception("dc_meet event=EMAIL_FAILED")


# --- The CSPs near DCs templates, with the DC button ------------------------------------

def make_templates(db: Session, source_names: List[str]) -> List[dict]:
    """
    Copies of approved templates with Meet the District Coordinator in place of Personal
    Guidance, as drafts named "<name> · CSPs near DCs", for the team to submit to Meta.
    """
    import uuid
    from src.models.whatsapp import WhatsAppTemplate
    from src.services import campaign_buttons
    made = []
    for name in source_names:
        t = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.name == name).first()
        if t is None:
            made.append({"source": name, "error": "not found"})
            continue
        new_name = f"{t.name} · CSPs near DCs"
        if db.query(WhatsAppTemplate).filter(WhatsAppTemplate.name == new_name).first():
            made.append({"source": name, "name": new_name, "status": "already there"})
            continue
        meta = ((t.meta_template_name or t.name).lower().replace(" ", "_")[:480] + "_neardc")
        copy = WhatsAppTemplate(template_id=uuid.uuid4().hex, name=new_name, meta_template_name=meta,
                                language_code=t.language_code, category=t.category or "MARKETING",
                                header_type=t.header_type, header_content=t.header_content, body=t.body,
                                footer=t.footer, buttons=campaign_buttons.near_dc_quick_replies(t.language_code),
                                status="Draft", target_state=getattr(t, "target_state", None))
        db.add(copy)
        made.append({"source": name, "name": new_name, "status": "Draft"})
    db.commit()
    return made
