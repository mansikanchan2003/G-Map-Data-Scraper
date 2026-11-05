"""
The language of someone's last message, so a nudge goes out in it (the team's
rule, 2026-10-21: "the nudge should be in the language used in the response
by the user in their last message").

The script says most of it: Gujarati letters are Gujarati, Gurmukhi is
Punjabi, and so on. Devanagari is Hindi unless the chat was in Marathi.
Latin letters are Hindi written in Latin letters (Hinglish) when they read
like it; Gujarati, Marathi, Punjabi or Bengali typed in Latin letters, often
mixed with English, when they read like one of those (the reply then goes in
that language's own script); English when they have English's own words;
otherwise the language they chose for the chat. A voice note carries the language it was heard in.
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

# Other languages as people type them in Latin letters, often mixed with English
# ("Mare potano business 6 aena mate Kai batao", 4 Nov 2026). Two words of one,
# more than the Hindi ones, make the message that language.
_LATIN_TYPED = {
    "gu": {"mare", "mara", "mari", "maru", "mane", "tame", "tamne", "tamaro", "tamari", "tamaru", "tamara", "ame",
           "amne", "amaro", "amaru", "che", "chhe", "chhu", "chu", "nathi", "kem", "shu", "su", "mate", "aena",
           "ena", "ene", "potano", "potani", "potanu", "kai", "kayi", "kevi", "kevu", "rite", "ketlu", "ketla",
           "ketli", "joie", "joiye", "karvu", "karvanu", "karva", "aapo", "apo", "saru", "haji", "ane", "thay",
           "thase", "thashe", "sakay", "shake", "majama", "batavo", "bataavo", "kyare", "kyathi", "kone", "malse",
           "malshe"},
    "mr": {"mala", "maza", "mazha", "majha", "maze", "majhe", "mazhe", "mazhi", "majhi", "tumhi", "tumcha", "tumchi", "aahe", "ahe", "aahet",
           "nahiye", "kay", "kasa", "kashi", "kase", "kiti", "kevha", "kuthe", "pahije", "havay", "sathi", "milel",
           "miltil", "lagel", "lagtil", "sanga", "sangaa", "kara", "karaycha", "karaychi", "hoil", "kaay", "tar",
           "pan", "ani"},
    "pa": {"mainu", "menu", "mennu", "tusi", "tuhanu", "tuhada", "tuhadi", "sanu", "assi", "kinna", "kinne",
           "kinni", "kiven", "kidda", "kive", "kado", "kadon", "kithe", "chahida", "chahidi", "hega", "haige",
           "milu", "lagu", "lagna", "dasso", "dass", "sat", "sri", "akal"},
    "bn": {"ami", "amar", "amake", "tumi", "tomar", "apni", "apnar", "koto", "kivabe", "kibhabe", "kobe",
           "kothay", "lagbe", "pabo", "pawa", "korbo", "korte", "chai", "ache", "achhe", "nei", "hobe", "bolun",
           "bolo", "jante"},
}
# Words only English uses. Without one, Latin letters are not taken for English:
# "business", "details", "call" or "CSP" are said inside every language.
_ENGLISH_WORDS = {
    "i", "me", "my", "you", "your", "we", "our", "the", "a", "an", "is", "am", "are", "was", "will", "would",
    "can", "could", "please", "want", "need", "what", "how", "when", "where", "which", "who", "why", "to",
    "for", "of", "in", "on", "and", "or", "not", "do", "does", "have", "has", "this", "that", "it",
    "thanks", "thank", "yes", "about", "with", "tell", "know",
}

_LATIN = re.compile(r"[A-Za-z]{2,}|\b[Ii]\b")


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
    typed = {lang: sum(w in vocab for w in words) for lang, vocab in _LATIN_TYPED.items()}
    # A tie goes to the language they chose for the chat.
    best = max(typed, key=lambda lang: (typed[lang], lang == chat_lang))
    if typed[best] >= 2 and typed[best] > hindi:
        return best, False
    if hindi >= 2 or (hindi and len(words) <= 3 and chat_lang == "hi"):
        return "hi", True
    # "ok" or "yes" says nothing about the language they would rather read.
    if len(words) < 2:
        return None
    if any(w in _ENGLISH_WORDS for w in words) or not chat_lang or chat_lang == "en":
        return "en", False
    # Latin letters but not English: their own language, typed in Latin letters. Keep the one they chose.
    return chat_lang, chat_lang == "hi"


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
