"""
A business's own WhatsApp bot answering our campaign ("Thank you for
reaching out to Royal Graphics… we will get back to you shortly"), told
apart from a person's reply (the user, 2026-10-26).

Shops reached by a campaign often have a greeting or away message set up in
WhatsApp Business. It answers within seconds, before anyone has read what we
sent, so it says nothing about their interest: the bot sends its greeting,
with Interested and Personal Guidance (onboarding_bot._auto_reply), so it
is the last thing in the chat when the owner opens it.

Read by fixed phrases, plus timing: a long message within a minute of the
campaign is not typed by a person.
"""
import re
from datetime import timedelta
from typing import Optional

# What greeting, away and out-of-office messages say, in English and the
# languages our campaigns go out in (Latin letters and native script).
_PHRASES = [
    r"thank(?:s| you) (?:so much |very much )?for (?:contacting|reaching|your (?:message|enquiry|inquiry|interest)|"
    r"messaging|connecting|writing|getting in touch|choosing|visiting)",
    r"\bwe(?: will|'ll| shall| would)? (?:get back|respond|reply|revert|contact you|connect with you|be in touch)",
    r"get back to you",
    r"(?:currently|presently|right now) (?:unavailable|away|closed|not available|offline)",
    r"\bout of (?:the )?office\b",
    r"\b(?:business|working|office|opening) hours\b",
    r"\bauto(?:mated)?[- ]?(?:reply|response|message)\b",
    r"\bthis is an automated\b",
    r"\bwill (?:reply|respond|contact you|call you back) (?:shortly|soon|as soon as)",
    # Hindi / Hinglish
    r"संपर्क करने के लिए (?:धन्यवाद|शुक्रिया)",
    r"जल्द ही (?:आपसे )?संपर्क",
    r"sampark karne ke liye (?:dhanyavaad|dhanyavad|dhanyawad|shukriya)",
    r"jald(?:i| hi) (?:aapse )?(?:sampark|contact)",
    # Gujarati
    r"સુધી પહોંચવા બદલ આભાર",
    r"સંપર્ક કરવા બદલ આભાર",
    r"ટૂંક સમયમાં (?:આપનો |તમારો )?સંપર્ક",
    # Marathi
    r"संपर्क साधल्याबद्दल धन्यवाद",
    # Bengali
    r"যোগাযোগ করার জন্য ধন্যবাদ",
    # Tamil / Telugu / Kannada
    r"தொடர்பு கொண்டதற்கு நன்றி",
    r"సంప్రదించినందుకు ధన్యవాదాలు",
    r"ಸಂಪರ್ಕಿಸಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು",
    # Punjabi
    r"ਸੰਪਰਕ ਕਰਨ ਲਈ ਧੰਨਵਾਦ",
]
_PATTERN = re.compile("|".join(f"(?:{p})" for p in _PHRASES), re.IGNORECASE)

# No person reads a campaign and types this much this fast.
FAST = timedelta(seconds=60)
FAST_LENGTH = 60


def matched(text: Optional[str]) -> Optional[str]:
    """The phrase that marks the text as automatic, or None."""
    found = _PATTERN.search(text or "")
    return found.group(0) if found else None


def is_automatic(text: Optional[str], sent_at=None, received_at=None) -> bool:
    """Whether a reply to our campaign came from their own bot, not a person."""
    if not (text or "").strip():
        return False
    if matched(text):
        return True
    if sent_at is not None and received_at is not None:
        quick = timedelta(0) <= received_at - sent_at <= FAST
        return quick and len(text.strip()) >= FAST_LENGTH
    return False


def missed(db) -> list:
    """
    Campaign chats whose last word is their shop's auto-reply, still
    unanswered, with the 24-hour window open: those that came in before the
    bot greeted them (or while a send was still being saved).
    """
    from src.models.inbox import WhatsAppConversation, WhatsAppMessage
    from src.services import inbox, onboarding_bot

    out = []
    convs = (db.query(WhatsAppConversation)
             .filter(WhatsAppConversation.bot_step.is_(None),
                     WhatsAppConversation.last_inbound_at >= inbox.now() - inbox.REPLY_WINDOW).all())
    for conv in convs:
        if not inbox.window_open(conv) or not inbox.from_campaign(db, conv.phone):
            continue
        last = (db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == conv.phone)
                .order_by(WhatsAppMessage.created_at.desc()).first())
        if last is None or last.direction != "IN" or last.kind != "text":
            continue
        sent = onboarding_bot.latest_send(db, conv.phone)
        if sent is None or (conv.bot_data or {}).get("auto_reply_for") == sent[0].recipient_id:
            continue
        if is_automatic(last.body, inbox.aware(sent[0].sent_at), inbox.aware(last.created_at)):
            out.append((conv, last))
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Greet the chats a shop's auto-reply answered")
    ap.add_argument("--send", action="store_true", help="send; without it, only list them")
    args = ap.parse_args(argv)
    from src.database import SessionLocal
    from src.services import onboarding_bot
    db = SessionLocal()
    try:
        found = missed(db)
        for conv, msg in found:
            print(f"{conv.phone}  {conv.profile_name or ''}  ->  {(msg.body or '')[:70]!r}")
            if args.send:
                onboarding_bot.handle(db, conv, msg)
                db.commit()
        print(f"{len(found)} chat(s) " + ("greeted." if args.send else "would be greeted. Add --send to send."))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
