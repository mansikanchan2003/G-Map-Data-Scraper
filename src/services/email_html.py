"""
Every AutoGMap email, with a designed look (20 Nov 2026): an Eko banner with an icon, a highlight
box for what matters most, cards with a coloured edge, icons beside each detail, coloured status
chips and buttons; all read from the plain-text body each email already writes.

How the text is read (the shape the emails already have):
  - the first paragraph is the lead sentence;
  - a line in CAPITALS (optionally "(...)" after it), or ending in ":", starts a section (a card);
  - "Label    value" (two or more spaces between) is a row; the first row of the first card is
    the highlight;
  - "- item" is a bullet, "1. item" a numbered step;
  - "Some words: https://..." is a button.
The subject gives the title; its last "· part" (Qualified, ESAF...) a coloured tag.
The plain text still goes with it, for mail apps that show no HTML.
"""
import html
import re
from typing import List, Optional, Tuple

TEAL, NAVY, GOLD = "#094053", "#0c2531", "#f9ab10"
TAGS = [  # (words in the tag, background, text)
    (("not in our", "outside", "rejected", "failed", "not qualified"), "#fde8e8", "#9b1c1c"),
    (("esaf",), "#ede9fe", "#5b21b6"),
    (("qualified", "submitted", "approved", "done", "solved"), "#def7ec", "#03543f"),
    (("dc visit", "wanted", "ticket", "attention", "needs"), "#fef3c7", "#92400e"),
]
TAG_NAMES = {"dc visit": "DC visit", "wanted": "Action needed", "ticket": "Ticket", "attention": "Needs attention",
             "needs": "Needs attention", "esaf": "ESAF", "qualified": "Qualified", "submitted": "Submitted",
             "approved": "Approved", "done": "Done", "solved": "Solved", "not in our": "Not in our SBI area",
             "outside": "Outside our SBI area", "rejected": "Rejected", "failed": "Failed", "not qualified": "Not qualified"}
# An icon for the title, by what the email is about.
TITLE_ICONS = [(("document",), "📄"), (("dc visit", "coordinator"), "🤝"), (("ticket", "attention", "question"), "🎫"),
               (("campaign", "approve"), "📣"), (("access", "sign"), "🔐"), (("guidance",), "💬")]
# An icon beside each detail, by its label.
ICONS = {"name": "👤", "phone": "📞", "available": "📅", "shop": "🏪", "place": "📍", "pin code": "📍", "pin": "📍",
         "applied for": "🏦", "education": "🎓", "investment": "💰", "aadhaar": "🪪", "verdict": "✅", "campaign": "📣",
         "note": "📝", "email": "✉️", "district": "📍", "state": "🗺️", "when": "🕒", "branch": "🏦", "language": "🗣️"}
EDGES = [TEAL, GOLD, "#7c3aed", "#059669", "#2563eb", "#db2777"]
# Words in a value that colour it as a chip.
CHIPS = [(("not qualified", "outside", "not verified", "cannot", "rejected"), "#fde8e8", "#9b1c1c"),
         (("esaf",), "#ede9fe", "#5b21b6"),
         (("strongly qualified", "qualified", "verified through digilocker", "can invest", "within"), "#def7ec", "#03543f")]
_ROW = re.compile(r"^\s*([^:\-\d][^:]{0,28}?)\s{2,}(\S.*)$")
_LINK = re.compile(r"^\s*(.{2,60}?):\s*(https?://\S+)\s*$")
_URL = re.compile(r"(https?://[^\s<]+)")
_CAPS = re.compile(r"^([A-Z][A-Z /&'-]{2,})(\s*\(.*\))?$")


def _esc(t: str) -> str:
    return _URL.sub(lambda m: f'<a href="{m.group(1)}" style="color:{TEAL};">{m.group(1)}</a>', html.escape(t))


def _tag(subject: str) -> Optional[Tuple[str, str, str]]:
    part = subject.rsplit("·", 1)[-1].strip() if "·" in subject else ""
    low = (part or subject).lower()
    for words, bg, fg in TAGS:
        if any(w in low for w in words):
            return (part or TAG_NAMES.get(next(w for w in words if w in low), "Update"), bg, fg)
    return None


def _title(subject: str) -> str:
    t = re.sub(r"^AutoGMap:\s*", "", subject).strip()
    return t.rsplit("·", 1)[0].strip() if "·" in t else t


def _title_icon(subject: str) -> str:
    low = subject.lower()
    return next((icon for words, icon in TITLE_ICONS if any(w in low for w in words)), "🔔")


def _icon(label: str) -> str:
    low = label.lower().strip()
    return ICONS.get(low) or next((v for k, v in ICONS.items() if k in low), "•")


def _value(v: str, shown: Optional[str] = None) -> str:
    low = v.lower()
    for words, bg, fg in CHIPS:
        if any(w in low for w in words):
            return (f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;background:{bg};color:{fg};'
                    f'font-size:13px;font-weight:700;">{_esc(shown or v)}</span>')
    return _esc(shown or v)


def render(subject: str, body: str, footer: Optional[str] = None, lang: str = "en") -> str:
    """The email's HTML from its English text; what is shown is put in `lang` (email_i18n)."""
    from src.services import email_i18n
    k = {"hi": 0, "hinglish": 1}.get(lang)

    def T(text: str) -> str:
        return email_i18n._one(text, k) if k is not None and text else text
    lines = (body or "").replace("\r", "").split("\n")
    lead: List[str] = []
    i = 0
    while i < len(lines) and lines[i].strip():          # the lead paragraph
        lead.append(lines[i].strip())
        i += 1
    cards: List[dict] = []
    buttons: List[Tuple[str, str]] = []
    current = {"heading": None, "items": []}

    def close():
        nonlocal current
        if current["items"] or current["heading"]:
            cards.append(current)
        current = {"heading": None, "items": []}

    for raw in lines[i:]:
        line = raw.rstrip()
        s = line.strip()
        if not s:
            continue
        link = _LINK.match(s)
        if link:
            buttons.append((link.group(1), link.group(2)))
            continue
        if _CAPS.match(s) or (s.endswith(":") and len(s) < 60 and "  " not in s):
            close()
            current["heading"] = s.rstrip(":")
            continue
        row = _ROW.match(line)
        m = re.match(r"^\s*(?:-|•)\s+(.*)$", line)
        n = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if row:
            current["items"].append(("row", row.group(1).strip(), row.group(2).strip()))
        elif m:
            current["items"].append(("bullet", m.group(1), None))
        elif n:
            current["items"].append(("step", n.group(1), n.group(2)))
        else:
            current["items"].append(("text", s, None))
    close()

    # The highlight: the first row of the first card that has rows.
    highlight = None
    for c in cards:
        rows = [x for x in c["items"] if x[0] == "row"]
        if rows:
            highlight = rows[0]
            c["items"].remove(rows[0])
            break

    def card_html(c: dict, k: int) -> str:
        edge = EDGES[k % len(EDGES)]
        head = (f'<div style="font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;font-weight:800;'
                f'color:{edge if edge != GOLD else "#b45309"};margin:0 0 10px;">{html.escape(T(c["heading"]))}</div>') if c["heading"] else ""
        parts, rows = [], []

        def flush_rows():
            if rows:
                parts.append('<table role="presentation" style="border-collapse:collapse;width:100%;">' + "".join(rows) + "</table>")
                rows.clear()
        for kind, a, b in c["items"]:
            if kind == "row":
                rows.append(f'<tr><td style="padding:7px 8px 7px 0;width:26px;font-size:16px;vertical-align:top;">{_icon(a)}</td>'
                            f'<td style="padding:7px 12px 7px 0;color:#5b7480;font-size:13px;white-space:nowrap;vertical-align:top;">{html.escape(T(a))}</td>'
                            f'<td style="padding:7px 0;color:{NAVY};font-size:14px;font-weight:600;">{_value(b, T(b))}</td></tr>')
                continue
            flush_rows()
            if kind == "bullet":
                parts.append(f'<div style="margin:6px 0;padding:9px 12px;border-radius:10px;background:#f4f8fa;color:{NAVY};font-size:14px;">'
                             f'<span style="color:{GOLD};font-weight:800;margin-right:8px;">●</span>{_esc(T(a))}</div>')
            elif kind == "step":
                parts.append(f'<div style="margin:8px 0;color:{NAVY};font-size:14px;line-height:1.5;"><span style="display:inline-block;'
                             f'min-width:24px;height:24px;line-height:24px;border-radius:12px;background:{TEAL};color:#fff;text-align:center;'
                             f'font-size:12px;font-weight:800;margin-right:10px;">{a}</span>{_esc(T(b))}</div>')
            else:
                parts.append(f'<p style="margin:0 0 8px;color:{NAVY};font-size:14px;line-height:1.6;">{_esc(T(a))}</p>')
        flush_rows()
        return (f'<div style="background:#ffffff;border:1px solid #dbe7ec;border-left:5px solid {edge};border-radius:14px;'
                f'padding:16px 18px;margin:0 0 14px;box-shadow:0 1px 3px rgba(12,37,49,.06);">{head}{"".join(parts)}</div>')

    tag = _tag(subject)
    tag_html = (f'<span style="display:inline-block;margin-top:12px;padding:5px 14px;border-radius:999px;background:{tag[1]};'
                f'color:{tag[2]};font-size:12.5px;font-weight:800;">{html.escape(email_i18n.TAGS.get(tag[0], (tag[0], tag[0]))[k] if k is not None else tag[0])}</span>') if tag else ""
    hl_html = ""
    if highlight:
        _, label, value = highlight
        hl_html = (f'<div style="background:linear-gradient(120deg,#fff7e0,#fffbeb);background-color:#fff7e0;border:1px solid #f6d77a;'
                   f'border-radius:14px;padding:16px 18px;margin:0 0 16px;">'
                   f'<div style="font-size:12px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#92400e;">'
                   f'{_icon(label)} &nbsp;{html.escape(T(label))}</div>'
                   f'<div style="font-size:22px;font-weight:800;color:{NAVY};margin-top:6px;line-height:1.3;">{_value(value, T(value))}</div></div>')
    btn_html = "".join(
        f'<a href="{html.escape(url)}" style="display:inline-block;margin:0 10px 10px 0;padding:13px 22px;border-radius:12px;'
        f'background:{TEAL if k == 0 else "#ffffff"};color:{"#ffffff" if k == 0 else TEAL};border:2px solid {TEAL};'
        f'font-size:14.5px;font-weight:800;text-decoration:none;">{html.escape(T(label))} &rarr;</a>'
        for k, (label, url) in enumerate(buttons))
    lead_html = "".join(f'<p style="margin:0 0 6px;font-size:16px;line-height:1.55;color:{NAVY};">{_esc(T(p))}</p>' for p in lead)
    foot = html.escape(footer or "Sent automatically by AutoGMap")
    return f"""<!doctype html><html><body style="margin:0;padding:0;background:#e8f0f3;">
<div style="max-width:640px;margin:0 auto;padding:24px 14px;font-family:'Segoe UI',Arial,Helvetica,sans-serif;">
  <div style="background:linear-gradient(125deg,{NAVY} 0%,{TEAL} 55%,#1d6b80 100%);background-color:{TEAL};border-radius:18px 18px 0 0;padding:22px 24px 24px;color:#ffffff;">
    <table role="presentation" style="border-collapse:collapse;width:100%;"><tr>
      <td style="vertical-align:middle;"><span style="font-size:22px;font-weight:900;color:{GOLD};letter-spacing:-.02em;">eko</span>
        <span style="font-size:11.5px;font-weight:800;letter-spacing:.18em;color:#cfe3ea;margin-left:6px;">AUTOGMAP</span></td>
      <td style="text-align:right;vertical-align:middle;"><span style="display:inline-block;width:46px;height:46px;line-height:46px;text-align:center;border-radius:14px;background:rgba(255,255,255,.14);font-size:24px;">{_title_icon(subject)}</span></td>
    </tr></table>
    <div style="font-size:23px;font-weight:800;line-height:1.3;margin-top:12px;">{html.escape(_title(T(subject)))}</div>
    {tag_html}
  </div>
  <div style="height:5px;background:linear-gradient(90deg,{GOLD},#ffd25e);background-color:{GOLD};"></div>
  <div style="background:#f5f9fa;border:1px solid #dbe7ec;border-top:0;border-radius:0 0 18px 18px;padding:22px 18px 10px;">
    {lead_html and f'<div style="margin:0 0 16px;">{lead_html}</div>'}
    {hl_html}
    {"".join(card_html(c, k) for k, c in enumerate(cards))}
    {btn_html and f'<div style="margin:10px 0 12px;">{btn_html}</div>'}
  </div>
  <div style="text-align:center;color:#7b929c;font-size:11.5px;padding:16px 8px;">
    <span style="color:{TEAL};font-weight:800;">Eko India Financial Services</span> &nbsp;·&nbsp; {foot}</div>
</div></body></html>"""
