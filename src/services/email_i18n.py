"""
Each person's emails in their own language (Mansi, 20 Nov 2026): Biswajit Sir in Hindi, Kavya
Ma'am in Hinglish, everyone else in English (EMAIL_LANGUAGES overrides, as
"email:lang,email:lang").

Only the emails' fixed words are put into the language: labels, headings, buttons, tags and the
sentences the app always writes the same way. What a person wrote, names, numbers, places and
shops stay as they are. A sentence with no translation here stays in English.
"""
import os
import re
from typing import Dict, List, Optional, Tuple

DEFAULT = {"biswajit@eko.co.in": "hi", "kavya.shukla@eko.co.in": "hinglish"}


def language_of(address: str) -> str:
    raw = os.environ.get("EMAIL_LANGUAGES")
    table = dict(DEFAULT)
    if raw:
        for part in raw.split(","):
            if ":" in part:
                a, l = part.split(":", 1)
                table[a.strip().lower()] = l.strip()
    return table.get((address or "").strip().lower(), "en")


# Whole lines or labels: English -> (Hindi, Hinglish).
WORDS: Dict[str, Tuple[str, str]] = {
    # labels
    "Available": ("उपलब्ध", "Available"),
    "Name": ("नाम", "Naam"),
    "Phone": ("फ़ोन", "Phone"),
    "Shop": ("दुकान", "Dukaan"),
    "Place": ("जगह", "Jagah"),
    "Note": ("नोट", "Note"),
    "Applied for": ("किसके लिए", "Kiske liye"),
    "Education": ("पढ़ाई", "Padhai"),
    "Investment": ("निवेश", "Investment"),
    "PIN code": ("पिन कोड", "PIN code"),
    "Aadhaar": ("आधार", "Aadhaar"),
    "Verdict": ("नतीजा", "Nateeja"),
    # headings
    "APPLICANT": ("आवेदक", "Applicant"),
    "NEAREST SBI BRANCH OF OURS": ("हमारी सबसे नज़दीकी SBI ब्रांच", "Hamari sabse nazdeeki SBI branch"),
    "NEXT STEPS": ("आगे क्या करना है", "Aage kya karna hai"),
    "NEAREST DISTRICT COORDINATORS": ("सबसे नज़दीकी District Coordinator", "Sabse nazdeeki District Coordinators"),
    "THE CHAT SO FAR": ("अब तक की बातचीत", "Ab tak ki baatcheet"),
    "Nearest District Coordinators": ("सबसे नज़दीकी District Coordinator", "Sabse nazdeeki District Coordinators"),
    "The chat so far": ("अब तक की बातचीत", "Ab tak ki baatcheet"),
    "Journey so far": ("अब तक का सफ़र", "Ab tak ka safar"),
    "AutoGMap does": ("AutoGMap अपने आप करता है", "AutoGMap khud karta hai"),
    # buttons
    "Open in AutoGMap": ("AutoGMap में खोलें", "AutoGMap mein kholein"),
    "Open the chat": ("चैट खोलें", "Chat kholein"),
    "WhatsApp": ("WhatsApp", "WhatsApp"),
    # values
    "SBI Customer Service Point": ("SBI ग्राहक सेवा केंद्र (CSP)", "SBI Customer Service Point"),
    "ESAF banking agent": ("ESAF बैंकिंग एजेंट", "ESAF banking agent"),
    "Can invest ₹3–5 lakh": ("₹3–5 लाख निवेश कर सकते हैं", "₹3–5 lakh invest kar sakte hain"),
    "Cannot invest ₹3–5 lakh": ("₹3–5 लाख निवेश नहीं कर सकते", "₹3–5 lakh invest nahi kar sakte"),
    "Not answered": ("जवाब नहीं दिया", "Jawab nahi diya"),
    "Graduate / Post-graduate": ("ग्रेजुएट / पोस्ट-ग्रेजुएट", "Graduate / Post-graduate"),
    "12th / Diploma": ("12वीं / डिप्लोमा", "12th / Diploma"),
    "Below 12th": ("12वीं से कम", "12th se kam"),
    "Verified through DigiLocker": ("DigiLocker से सत्यापित", "DigiLocker se verified"),
    "Not verified through DigiLocker (uploaded as a file)": ("DigiLocker से सत्यापित नहीं (फ़ाइल अपलोड की)", "DigiLocker se verified nahi (file upload ki)"),
    "Not given yet": ("अभी नहीं दिया", "Abhi nahi diya"),
    "Strongly qualified": ("पूरी तरह योग्य", "Poori tarah qualified"),
    "Not qualified for SBI branch code": ("SBI ब्रांच कोड के लिए योग्य नहीं", "SBI branch code ke liye qualified nahi"),
    "Not qualified": ("योग्य नहीं", "Qualified nahi"),
    "PIN qualified": ("हमारे SBI क्षेत्र में", "Hamare SBI area mein"),
    # fixed sentences
    "Hand over to Eko Acquisition: assign a DC and schedule the visit.":
        ("Eko Acquisition को सौंपें: एक DC तय करें और विज़िट शेड्यूल करें।", "Eko Acquisition ko saunpiye: ek DC assign karke visit schedule kariye."),
    "Check the documents in the Inbox and call them to finish what is missing.":
        ("Inbox में दस्तावेज़ देखें और जो बाकी है उसे पूरा कराने के लिए कॉल करें।", "Inbox mein documents dekhiye aur jo baaki hai use poora karwane ke liye call kariye."),
    "Below 12th: not eligible for SBI or ESAF. Thank them and close politely.":
        ("12वीं से कम: SBI या ESAF के लिए योग्य नहीं। धन्यवाद कहकर विनम्रता से बात खत्म करें।", "12th se kam: SBI ya ESAF ke liye eligible nahi. Dhanyavaad bolkar politely baat khatam kariye."),
    "Arrange Aceware's shop verification and the agent agreement on ₹100 stamp paper.":
        ("Aceware की दुकान जाँच और ₹100 के स्टांप पेपर पर एजेंट एग्रीमेंट तय करें।", "Aceware ka shop verification aur ₹100 stamp paper par agent agreement arrange kariye."),
    "The documents are in AutoGMap's Inbox; they are not attached to this email.":
        ("दस्तावेज़ AutoGMap के Inbox में हैं; इस ईमेल के साथ नहीं जोड़े गए।", "Documents AutoGMap ke Inbox mein hain; is email ke saath attach nahi hain."),
}

# Sentences with a part that changes: (pattern, Hindi, Hinglish); groups are kept as they are.
PATTERNS: List[Tuple[str, str, str]] = [
    (r"^(.+) wants our District Coordinator to visit them\.$",
     r"\1 चाहते हैं कि हमारे District Coordinator उनसे मिलने आएँ।", r"\1 chahte hain ki hamare District Coordinator unse milne aayein."),
    (r"^(.+) has completed the journey and uploaded their documents \((.+) IST\)\.$",
     r"\1 ने पूरी प्रक्रिया पूरी कर ली है और अपने दस्तावेज़ अपलोड कर दिए हैं (\2 IST)।", r"\1 ne poora process complete kar liya hai aur apne documents upload kar diye hain (\2 IST)."),
    (r"^(.+) has completed the journey and uploaded their documents\.$",
     r"\1 ने पूरी प्रक्रिया पूरी कर ली है और अपने दस्तावेज़ अपलोड कर दिए हैं।", r"\1 ne poora process complete kar liya hai aur apne documents upload kar diye hain."),
    (r"^(.+) needs a reply on WhatsApp\.(.*)$",
     r"\1 को WhatsApp पर जवाब चाहिए।\2", r"\1 ko WhatsApp par jawab chahiye.\2"),
    (r"^To do \(the sheet\): (.+)$", r"क्या करना है: \1", r"Kya karna hai: \1"),
    (r"^DOCUMENTS \((\d+) on the upload form(?:, (\d+) files in the chat)?\)$",
     r"दस्तावेज़ (अपलोड फ़ॉर्म पर \1)", r"Documents (upload form par \1)"),
    (r"^Strongly qualified for SBI: (.+)\.$", r"SBI के लिए पूरी तरह योग्य: \1।", r"SBI ke liye poori tarah qualified: \1."),
    # subjects
    (r"^AutoGMap: DC visit wanted — (.+)$", r"AutoGMap: DC विज़िट चाहिए — \1", r"AutoGMap: DC visit chahiye — \1"),
    (r"^AutoGMap: (.+) submitted documents · (.+)$", r"AutoGMap: \1 ने दस्तावेज़ भेजे · \2", r"AutoGMap: \1 ne documents bheje · \2"),
]
TAGS = {"Qualified": ("योग्य", "Qualified"), "ESAF": ("ESAF", "ESAF"),
        "Not in our SBI area": ("हमारे SBI क्षेत्र से बाहर", "Hamare SBI area se bahar")}


def _one(text: str, k: int) -> str:
    s = text.strip()
    if s in WORDS:
        return text.replace(s, WORDS[s][k])
    for pat, hi, hing in PATTERNS:
        if re.match(pat, s):
            return text.replace(s, re.sub(pat, (hi, hing)[k], s))
    return text


_ROW = re.compile(r"^(\s*)([^:\-\d][^:]{0,28}?)(\s{2,})(\S.*)$")
_LINK = re.compile(r"^(\s*)(.{2,60}?):(\s*https?://\S+\s*)$")


def translate(subject: str, body: str, lang: str) -> Tuple[str, str]:
    """(subject, body) in this language; English as it was for "en" or an unknown one."""
    if lang not in ("hi", "hinglish"):
        return subject, body
    k = 0 if lang == "hi" else 1
    sub = _one(subject, k)
    if "·" in sub:
        head, tag = sub.rsplit("·", 1)
        if tag.strip() in TAGS:
            sub = f"{head}· {TAGS[tag.strip()][k]}"
    out = []
    for line in (body or "").split("\n"):
        link = _LINK.match(line)
        row = _ROW.match(line)
        if link and link.group(2).strip() in WORDS:
            out.append(f"{link.group(1)}{WORDS[link.group(2).strip()][k]}:{link.group(3)}")
        elif row and row.group(2).strip() in WORDS:
            label = WORDS[row.group(2).strip()][k]
            out.append(f"{row.group(1)}{label}{row.group(3)}{_one(row.group(4), k)}")
        else:
            m = re.match(r"^(\s*(?:\d+\.|-)\s+)(.*)$", line)
            out.append(m.group(1) + _one(m.group(2), k) if m else _one(line, k))
    return sub, "\n".join(out)


def footer(lang: str) -> Optional[str]:
    return {"hi": "AutoGMap द्वारा अपने आप भेजा गया", "hinglish": "AutoGMap ne khud bheja"}.get(lang)
