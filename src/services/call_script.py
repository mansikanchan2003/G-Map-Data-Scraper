"""
One lead on one page, for the person calling them (Kavya Ma'am's Summary button, 19 Nov 2026):
what happened in the chat, everything they told us (PIN, education, investment, documents...),
and a warm, polite, empathetic call script in Hinglish for where they are now.

Fixed text built from what we know; no language model. The script keeps Eko's word rules:
₹3–5 lakh (depending on location), no fixed income, no commission figures; for ESAF the
₹1,999 registration and "koi bada investment nahi".
"""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.inbox import WhatsAppConversation
from src.services import applications, call_plan, chat_summary, dispositions as dz
from src.services import onboarding_bot as bot

LANGUAGE = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish", "gu": "Gujarati", "mr": "Marathi", "pa": "Punjabi",
            "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam", "or": "Odia"}


def _app(db: Session, phone: str) -> Optional[dict]:
    for removed in (False, True):
        hit = next((a for a in applications.list_applications(db, removed=removed)["items"] if a["phone"] == phone), None)
        if hit:
            return hit
    return None


def _branch_text(b: Optional[dict]) -> str:
    """"SBI Jasdan · code 60077 · AO Rajkot · 26.9 km from their PIN (outside our 20 km)"."""
    if not b:
        return "Pata nahi (PIN abhi map par nahi mila)"
    within = b["distance_km"] <= applications.SBI_RADIUS_KM
    return (f"SBI {b.get('branch_name')} · code {b.get('branch_code')}" + (f" · AO {b['ao']}" if b.get("ao") else "")
            + f" · unke PIN se {b['distance_km']} km"
            + (f" (hamare {applications.SBI_RADIUS_KM:g} km ke andar: SBI ke liye theek)" if within
               else f" ({applications.SBI_RADIUS_KM:g} km se bahar: SBI nahi, ESAF offer karein)"))


def _facts(a: dict, conv: WhatsAppConversation) -> List[Dict[str, str]]:
    yes_no = lambda v, yes, no: yes if v is True else no if v is False else "Abhi bataya nahi"  # noqa: E731
    place = ", ".join(x for x in (a.get("tehsil"), a.get("district"), a.get("state")) if x)
    rows = [
        ("Programme", "ESAF banking agent mein interested" if a["programme"] == "esaf" else "SBI CSP (Kiosk Operator) ke liye"),
        ("PIN code", " · ".join(x for x in (a.get("pincode"), place) if x) or "Abhi bataya nahi"),
        ("Nearest SBI branch", _branch_text(a.get("nearest_sbi"))),
        ("Padhai", a.get("qualification") or "Abhi bataya nahi"),
        ("₹3–5 lakh invest", yes_no(a.get("can_invest"), "Haan, kar sakte hain", "Nahi kar sakte")),
        ("Pehle franchise / business", yes_no(a.get("franchise_background"), "Haan", "Nahi")),
        ("Bhasha", LANGUAGE.get(a.get("language") or "", "Pata nahi")),
        ("Abhi kahan hain", a.get("stage") or "—"),
        ("Documents", f"{a['documents_count']} / {a['documents_total']} upload" + (" (sab zaroori aa gaye)" if a.get("required_documents_done") else "")),
        ("Eligible?", a.get("verdict") or "—"),
        ("Unki dukaan", " · ".join(x for x in ((a.get("source") or {}).get("business_name"), a.get("category")) if x) or "—"),
    ]
    if a.get("near_dc"):
        rows.insert(2, ("Area", "CSPs near DCs (SBI CSP centre ke paas)"))
    if conv.disposition:
        rows.append(("Abhi ka outcome", dz.label(conv.disposition) or conv.disposition))
    return [{"label": k, "value": v} for k, v in rows]


def _script(a: dict, conv: WhatsAppConversation, questions: List[str], missing: List[str]) -> List[dict]:
    name = (a.get("name") or "").split(" ")[0] or ""
    ji = f"{name} ji" if name else "ji"
    esaf = a["programme"] == "esaf"
    what = "ESAF Small Finance Bank ka banking agent banne" if esaf else "SBI Customer Service Point (CSP) kholne"
    opening = [
        f"Namaste {ji}, main Eko se {{aapka naam}} baat kar rahi hoon. Kya abhi 2-3 minute baat karna theek rahega?",
        f"Aapne WhatsApp par {what} mein interest dikhaya tha, uske liye bahut shukriya. Main bas aapki madad karne ke liye call kar rahi hoon.",
        "(Agar abhi busy hain: \"Koi baat nahi, aapke liye kaun sa time theek rahega? Main tab call kar loongi.\")",
    ]
    listen = [
        "Pehle unhe bolne dein: \"Aap batayiye, aapke mann mein kya sawaal hain?\"",
        "Jo woh pehle bata chuke hain (upar), woh dobara na poochhein; bas confirm karein: \"Aapne bataya tha ki…, sahi hai na?\"",
    ]
    if questions:
        listen.append("Unke sawaal, jinka jawab dena hai: " + " · ".join(f"“{q}”" for q in questions[:4]))
    stage = call_plan._stage_talk(conv.bot_step, conv.bot_data or {}, missing)
    talk = [f"Is call ka maqsad: {stage['goal']}."] + list(stage["points"])
    if esaf:
        talk = ["Is call ka maqsad: ESAF registration aage badhana.",
                "ESAF mein koi bada investment nahi: sirf ₹1,999 registration; Micro ATM chahiye to ₹1,300 + GST alag.",
                "Services: AEPS, Micro ATM, money transfer, bill payment, recharge, account opening.",
                "Documents: Aadhaar, PAN, bank proof, dukaan ki photo aur 12th ya usse upar ki marksheet."]
    if missing:
        talk.append("Abhi ye documents baaki hain: " + ", ".join(missing) + ". Unhe batayein ki WhatsApp ke upload link se aaram se bhej sakte hain.")
    worries = [
        "Paise ki chinta ho: \"Main samajh sakti hoon, ye ek bada faisla hai.\" SBI ke liye ₹3–5 lakh (location ke hisaab se), aur ye paisa unke apne e-wallet mein rehta hai jisse woh grahakon ka kaam karte hain. Agar abhi itna nahi ho sakta, to ESAF ka option batayein (₹1,999 registration).",
        "Bharosa na ho: \"Aapka sawaal bilkul sahi hai.\" Eko 17+ saal se SBI ka Business Correspondent hai, 1,100+ CSP chal rahe hain; kiosk.eko.in par khud dekh sakte hain.",
        "Documents mein dikkat ho: \"Koi jaldi nahi, main aapke saath hoon.\" Aadhaar DigiLocker se apne aap aa jata hai; baaki ki photo WhatsApp link par bhej sakte hain.",
        "Samay na ho: \"Bilkul, aap apna time bataiye.\" Callback ka time note karein.",
    ]
    close = [
        "Agla kadam saaf batayein, ek hi baat: " + (
            "documents upload karna." if missing or conv.bot_step in (bot.AWAIT_DOCS, bot.AWAIT_UPLOAD) else
            "₹1,999 registration aur shop verification." if esaf else
            "documents ki taiyaari aur upload link." if a.get("can_invest") else "aage ka option tay karna."),
        f"\"Aapka samay dene ke liye bahut shukriya, {ji}. Koi bhi sawaal ho to isi WhatsApp number par likh dijiye, hum hamesha madad ke liye hain.\"",
        "Call ke baad outcome record karein (Inbox → Disposition), aur yahan Comment likh dein.",
    ]
    return [
        {"title": "Shuruaat", "icon": "waving_hand", "lines": opening},
        {"title": "Unki baat suniye", "icon": "hearing", "lines": listen},
        {"title": "Kya batana hai", "icon": "record_voice_over", "lines": talk},
        {"title": "Agar woh chinta jatayein", "icon": "volunteer_activism", "lines": worries},
        {"title": "Baat khatam karte waqt", "icon": "handshake", "lines": close},
    ]


def brief(db: Session, phone: str) -> dict:
    conv = db.get(WhatsAppConversation, phone)
    a = _app(db, phone) if conv is not None else None
    if conv is None or a is None:
        raise LookupError("No such application")
    s = chat_summary.summarise(db, conv)
    missing = call_plan._missing_docs(db, conv) if conv.bot_step else []
    questions = [q["text"] for q in s.get("waiting_questions") or []] + [
        q["text"] for q in (s.get("questions") or []) if not q.get("answered_by_bot")]
    questions = list(dict.fromkeys(q for q in questions if q))
    return {
        "phone": phone, "name": a.get("name"), "programme": a["programme"],
        "headline": s.get("headline"), "in_short": s.get("in_short"),
        "story": (s.get("story") or [])[:8],
        "facts": _facts(a, conv),
        "their_questions": questions[:6],
        "missing_documents": missing,
        "script": _script(a, conv, questions, missing),
        "avoid": call_plan.AVOID + ["Commission ka koi figure na batayein.", "\"Zero investment\" ya \"mini bank\" na kahein."],
        "comments": a.get("comments") or [],
    }
