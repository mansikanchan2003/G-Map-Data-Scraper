"""
The language of someone's last message, so a nudge goes out in it (the team's
rule, 2026-10-21: "the nudge should be in the language used in the response
by the user in their last message").

The script says most of it: Gujarati letters are Gujarati, Gurmukhi is
Punjabi, and so on. Devanagari is Hindi unless the chat was in Marathi.
Latin letters are Hindi written in Latin letters (Hinglish) when they read
like it, else English. A voice note carries the language it was heard in.
With nothing to read, the bot's own language for the chat is used.
"""
import re
from typing import Optional, Tuple

from src.models.inbox import WhatsAppConversation, WhatsAppMessage

# Unicode blocks of the scripts the bot writes, and the language each means.
_SCRIPTS = [
    (r"[઀-૿]", "gu"),
    (r"[਀-੿]", "pa"),
    (r"[ঀ-৿]", "bn"),
    (r"[଀-୿]", "or"),
    (r"[஀-௿]", "ta"),
    (r"[ఀ-౿]", "te"),
    (r"[ಀ-೿]", "kn"),
    (r"[ഀ-ൿ]", "ml"),
    (r"[ऀ-ॿ]", "hi"),
]

# Common Hindi words as people type them in Latin letters. Two of them make a
# message Hinglish; English shares none of them.
_HINGLISH_WORDS = {
    "hai", "hain", "hoon", "hu", "hun", "kya", "kyu", "kyun", "kaise", "kese", "kaun", "kon", "kab", "kahan",
    "nahi", "nhi", "nahin", "haan", "ha", "mujhe", "mera", "meri", "mere", "aap", "aapka", "aapki", "apna",
    "karna", "karni", "karo", "karein", "kar", "raha", "rahi", "rahe", "tha", "thi", "chahiye", "chahta",
    "chahti", "sakta", "sakti", "bhi", "abhi", "baad", "mein", "ka", "ki", "ke", "ko", "se", "par",
    "bhai", "ji", "theek", "thik", "accha", "achha", "acha", "batao", "bataiye", "paisa", "kitna", "kitne",
    "lagega", "milega", "jankari", "samay", "kal", "aaj", "baat", "wala", "wali", "liye",
}

_LATIN = re.compile(r"[A-Za-z]{2,}")


def _said(msg: WhatsAppMessage) -> Optional[str]:
    if msg.kind == "text":
        return msg.body
    if msg.kind == "audio":
        return (msg.payload or {}).get("transcript")
    # A button tap's title is the button's wording, not theirs.
    return None


def of_text(text: Optional[str], chat_lang: Optional[str] = None) -> Optional[Tuple[str, bool]]:
    """(language, written in Latin letters) for a piece of text; None if it says nothing."""
    if not text:
        return None
    for pattern, lang in _SCRIPTS:
        if re.search(pattern, text):
            return ("mr" if lang == "hi" and chat_lang == "mr" else lang), False
    words = [w.lower() for w in _LATIN.findall(text)]
    if not words:
        return None
    hindi = sum(w in _HINGLISH_WORDS for w in words)
    if hindi >= 2 or (hindi and len(words) <= 3 and chat_lang == "hi"):
        return "hi", True
    # "ok" or "yes" says nothing about the language they would rather read.
    if len(words) < 2:
        return None
    return "en", False


def last_reply(db, conv: WhatsAppConversation) -> Tuple[str, bool]:
    """
    (language, Hindi in Latin letters) of the person's latest message that
    says anything, else the language the bot uses in this chat.
    """
    from src.services import onboarding_bot as bot

    chat_lang = bot._lang(db, conv)
    recent = (db.query(WhatsAppMessage)
              .filter(WhatsAppMessage.phone == conv.phone, WhatsAppMessage.direction == "IN")
              .order_by(WhatsAppMessage.created_at.desc()).limit(5).all())
    for msg in recent:
        heard = (msg.payload or {}).get("language") if msg.kind == "audio" else None
        if heard in ("hi", "en", "gu", "pa", "mr", "bn", "ta", "te", "kn", "ml", "or"):
            return heard, False
        found = of_text(_said(msg), chat_lang)
        if found:
            return found
    return chat_lang, (conv.bot_data or {}).get("script") == "latin" and chat_lang == "hi"
