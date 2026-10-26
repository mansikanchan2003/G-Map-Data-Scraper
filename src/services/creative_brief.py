"""
The standing brief the template agent works from.

Everything the agent must never get wrong lives here rather than in a prompt
string: the language each state is written in, the facts a template may claim,
and the rules every image must satisfy. The prompt is built from this, the
validator checks against it, and the Studio shows it — so what the agent is
told, what it is held to and what a reviewer reads are the same list.
"""
import re
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# State -> language
# ---------------------------------------------------------------------------
# Meta fixes a template's language at approval, so this decides both what the
# copy is written in and the code it is registered under. Every Hindi template
# sent so far was registered as en_US; that is the mistake this closes off.
#
# Keys are lower-cased state names as stored on locations and businesses.
STATE_LANGUAGES: Dict[str, str] = {
    "uttar pradesh": "hi",
    "haryana": "hi",
    "rajasthan": "hi",
    "bihar": "hi",
    "madhya pradesh": "hi",
    "delhi": "hi",
    "uttarakhand": "hi",
    "himachal pradesh": "hi",
    "jharkhand": "hi",
    "chhattisgarh": "hi",
    "punjab": "pa",
    "gujarat": "gu",
    "maharashtra": "mr",
    "west bengal": "bn",
    "tamil nadu": "ta",
    "telangana": "te",
    "andhra pradesh": "te",
    "karnataka": "kn",
    "kerala": "ml",
    "odisha": "or",
    "orissa": "or",
}

# Meta language code -> what the language is called, its script, the Unicode
# block that script occupies, and the font the poster is set in.
LANGUAGES: Dict[str, dict] = {
    "hi": {"name": "Hindi", "script": "Devanagari", "range": "ऀ-ॿ", "font": "Noto Sans Devanagari"},
    "mr": {"name": "Marathi", "script": "Devanagari", "range": "ऀ-ॿ", "font": "Noto Sans Devanagari"},
    "pa": {"name": "Punjabi", "script": "Gurmukhi", "range": "਀-੿", "font": "Noto Sans Gurmukhi"},
    "gu": {"name": "Gujarati", "script": "Gujarati", "range": "઀-૿", "font": "Noto Sans Gujarati"},
    "bn": {"name": "Bengali", "script": "Bengali", "range": "ঀ-৿", "font": "Noto Sans Bengali"},
    "ta": {"name": "Tamil", "script": "Tamil", "range": "஀-௿", "font": "Noto Sans Tamil"},
    "te": {"name": "Telugu", "script": "Telugu", "range": "ఀ-౿", "font": "Noto Sans Telugu"},
    "kn": {"name": "Kannada", "script": "Kannada", "range": "ಀ-೿", "font": "Noto Sans Kannada"},
    "ml": {"name": "Malayalam", "script": "Malayalam", "range": "ഀ-ൿ", "font": "Noto Sans Malayalam"},
    "or": {"name": "Odia", "script": "Odia", "range": "଀-୿", "font": "Noto Sans Oriya"},
}

# Languages Meta's templates do not list, and the code they are registered
# under instead. Meta reads the code as a label, not the script: the team's
# Hindi templates went in as en_US and were all approved. A template is
# written, checked and set in its own script whatever it is registered as.
META_LANGUAGE_FALLBACK: Dict[str, str] = {"or": "en_US"}


def meta_language(code: Optional[str]) -> Optional[str]:
    """The language code a template is registered with at Meta."""
    return META_LANGUAGE_FALLBACK.get(code, code)

# Every Indic block, so text in the wrong script can be caught — a Punjabi
# poster already went out with a Hindi heading on it. The danda (। ॥) sits in
# the Devanagari block but ends sentences in Punjabi and other scripts too, so
# it is not evidence of Devanagari.
_INDIC_BLOCKS = {
    "Devanagari": "ऀ-ॣ०-ॿ",
    "Bengali": "ঀ-৿",
    "Gurmukhi": "਀-੿",
    "Gujarati": "઀-૿",
    "Odia": "଀-୿",
    "Tamil": "஀-௿",
    "Telugu": "ఀ-౿",
    "Kannada": "ಀ-೿",
    "Malayalam": "ഀ-ൿ",
}

# ---------------------------------------------------------------------------
# Facts a template may state. Nothing outside this list is to be claimed.
# ---------------------------------------------------------------------------
PHONE = "+91 7291988625"
SIGNUP_URL = "kiosk.eko.in/signup"

FACTS: List[str] = [
    "Eko offers the chance to become an SBI Kiosk Operator / CSP (Customer Service Point, "
    "also called Customer Service Provider) and run a banking service point in your own area.",
    "Services the kiosk offers customers: opening a new SBI bank account, cash withdrawal, "
    "money transfer, balance enquiry.",
    "The kiosk can also help customers enrol in government schemes: PMJDY, PMJJBY, PMSBY, APY.",
    "Earning: an OPPORTUNITY to earn ₹15,000 to ₹50,000 commission per month. Always phrase as an "
    "opportunity ('कमाने का अवसर'), never as a guarantee.",
    "Applying is free (never ask anyone to pay for an allotment); Eko gives training, live support, "
    "installs the devices and runs every process for the operator's month-on-month growth.",
    "The investment is ₹3-5 lakh, depending on location and setup. The Banking Outlet needs its "
    "own space and fixed hours, so it suits established business families adding a second, respected "
    "business, and it draws on their name, network and existing customers.",
    "Women operators get an extra incentive on their total commission, up to a limit.",
    "Of the ₹3-5 lakh, about ₹1-1.5 lakh goes on the devices (laptop or tab, biometric device, micro "
    "ATM, passbook printer, GPS dongle), which Eko provides and trains the operator on. Part of the money stays "
    "with the operator, in their own e-wallet, which customers' transactions run through: a deposit or transfer is paid in cash "
    "to the operator and goes from the e-wallet to the customer's account, a withdrawal is paid out in cash and "
    "comes back into the e-wallet, and the operator tops it up at the bank with the cash collected; in the evening "
    "the amount transacted is added back to the e-wallet. A commission "
    "on every transaction. The rest sets up the outlet (seating, drinking water, posters, banners) so it looks "
    "like an SBI mini branch.",
    "Eko Bharat Ventures Private Limited has been a National Business Correspondent since 2009.",
    f"Contact by call or WhatsApp: {PHONE}.",
    f"Apply online: {SIGNUP_URL}.",
]

COPY_RULES: List[str] = [
    "Write every piece of customer-facing text in the state's language and script. Only brand "
    "and product words stay in Latin: Eko, SBI, Kiosk, CSP, Customer Service Point, WhatsApp, "
    "PMJDY, PMJJBY, PMSBY, APY, and the phone number.",
    "Use only the facts listed. Do not invent numbers, offers, deadlines, fees or partner names.",
    "Never guarantee income; earning is always an opportunity.",
    "The message body carries no URL — the Apply button holds the tracked link.",
    "The body is a WhatsApp message: short paragraphs, *bold* for emphasis, a few emojis, a "
    "respectful greeting and a thank-you. At most 900 characters.",
    "Each variant tests one clear idea (its angle) so its results can be compared with others.",
    "Never call it a job (naukri, vacancy, bharti, joining) or promise a salary, fixed, guaranteed or "
    "'pakka' income; no 'zero investment', 'limited seats' or pressure to pay; the operator is a Kiosk "
    "Operator, not a bank employee; write Eko as 'Eko'.",
]

IMAGE_RULES: List[str] = [
    "The photo must look like a real photograph, not AI art: candid documentary style, natural "
    "light, real skin texture, everyday clutter, no glossy or cartoon look.",
    "The Eko logo appears on every poster.",
    "Every poster shows an SBI Customer Service Point with an operator serving a customer.",
    "All poster text is in the state's language, including the SBI signboard.",
    "The photo itself contains no text, letters, signs or logos — the signboard and every word "
    "are set by the renderer, so spelling in the state's script is always correct.",
    f"The footer always shows {PHONE} and {SIGNUP_URL}.",
    "Layout follows the existing Eko posters: logo top-left, two-line headline with one "
    "highlighted phrase, callout box, six benefit icons, apply button, navy contact footer.",
]

# The ideas a variant can bet on. Each variant in a round takes a different
# one, so a round is a real comparison rather than one message reworded — the
# first live round wrote two Gujarati variants on the same idea when merely
# asked to differ. Results are compared per angle, so the keys stay stable.
ANGLES: Dict[str, str] = {
    "extra_income": "Extra monthly income alongside the shop or work you already have",
    "community_respect": "Respect and standing from serving your own village or neighbourhood",
    "trust_in_sbi": "The trust and pride of being associated with SBI, India's biggest bank",
    "government_schemes": "Helping neighbours join PMJDY, PMJJBY, PMSBY and APY",
    "easy_start": "Easy application, training and live support — no banking background needed",
    "area_banker_pride": "Becoming the whole area's trusted banker: 'poore ilaake ka banker', where the bank's name is, your name is",
    "next_generation_business": "A second respected business for the next generation of an established business family",
    "many_earning_lines": "Many ways to earn from one counter: accounts, schemes, deposits, loans, insurance, each with its own commission",
    "woman_entrepreneur": "A woman's own identity and standing as the area's banker, with an extra incentive for women operators",
    "eko_growth_promise": "Never alone: Eko runs every process (training, coaching, campaigns, devices, compliance) for month-on-month growth",
    "season_proof_income": "Earnings every month, in season or out, for agri-input, fuel and seasonal businesses",
    "network_advantage": "Your existing customers and contacts become your first kiosk customers",
    "convenience_for_locals": "Saving local people the trip to a distant bank branch",
}

# Icons the poster can show beside a benefit, keyed by the name the model picks.
# Values are Material Symbols names.
BENEFIT_ICONS: Dict[str, str] = {
    "application": "description",
    "support": "support_agent",
    "banking": "account_balance",
    "income": "currency_rupee",
    "growth": "trending_up",
    "secure": "verified_user",
    "network": "groups",
    "schemes": "volunteer_activism",
    "account": "person_add",
    "transfer": "sync_alt",
    "withdrawal": "payments",
    # Balance enquiry is one of the services; the agent kept reaching for it.
    "balance": "account_balance_wallet",
    "fingerprint": "fingerprint",
}


# The poster's fixed labels, written once per language instead of by the
# model. They are the same on every poster, and they are where the model
# slipped into other scripts: a Gujarati poster went out with the bank's name
# in Hindi and "Call / WhatsApp:" in Punjabi. Languages missing here are
# still written by the model and checked like any other text.
POSTER_LABELS: Dict[str, Dict[str, str]] = {
    "hi": {"sign_title": "ग्राहक सेवा केंद्र", "bank_name": "भारतीय स्टेट बैंक",
           "phone_label": "कॉल / WhatsApp:", "web_label": "ऑनलाइन आवेदन:"},
    "mr": {"sign_title": "ग्राहक सेवा केंद्र", "bank_name": "भारतीय स्टेट बँक",
           "phone_label": "कॉल / WhatsApp:", "web_label": "ऑनलाइन अर्ज:"},
    "pa": {"sign_title": "ਗਾਹਕ ਸੇਵਾ ਕੇਂਦਰ", "bank_name": "ਭਾਰਤੀ ਸਟੇਟ ਬੈਂਕ",
           "phone_label": "ਕਾਲ / WhatsApp:", "web_label": "ਆਨਲਾਈਨ ਅਪਲਾਈ:"},
    "gu": {"sign_title": "ગ્રાહક સેવા કેન્દ્ર", "bank_name": "ભારતીય સ્ટેટ બેંક",
           "phone_label": "કૉલ / WhatsApp:", "web_label": "ઓનલાઇન અરજી:"},
    "bn": {"sign_title": "গ্রাহক সেবা কেন্দ্র", "bank_name": "ভারতীয় স্টেট ব্যাংক",
           "phone_label": "কল / WhatsApp:", "web_label": "অনলাইন আবেদন:"},
    "or": {"sign_title": "ଗ୍ରାହକ ସେବା କେନ୍ଦ୍ର", "bank_name": "ଭାରତୀୟ ଷ୍ଟେଟ ବ୍ୟାଙ୍କ",
           "phone_label": "କଲ / WhatsApp:", "web_label": "ଅନଲାଇନ ଆବେଦନ:"},
}


def language_for_state(state: Optional[str]) -> Optional[str]:
    """Meta language code for a state, or None when no language is set for it."""
    return STATE_LANGUAGES.get((state or "").strip().lower())


def script_problems(text: str, language_code: str, *, require_script: bool = True) -> List[str]:
    """
    What is wrong with the script a piece of text is written in.

    Latin is always allowed — brand words, numbers and the phone number are
    written in it. Any other Indic script is not, and a field that should be
    localised must contain at least some of the target script.
    """
    lang = LANGUAGES[language_code]
    problems = []
    for script, block in _INDIC_BLOCKS.items():
        # By name: Devanagari's block here leaves out the danda, so it never
        # equals Hindi's range and Hindi text was flagged as foreign script.
        if script == lang["script"]:
            continue
        found = re.findall(f"[{block}]", text or "")
        if found:
            problems.append(f"contains {script} characters ({''.join(found[:12])}) in a {lang['name']} template")
    if require_script and not re.search(f"[{lang['range']}]", text or ""):
        problems.append(f"has no {lang['script']} text")
    return problems


def rules_for_display() -> dict:
    """The brief as the Studio shows it to a reviewer."""
    return {
        "facts": FACTS,
        "copy_rules": COPY_RULES,
        "image_rules": IMAGE_RULES,
        "state_languages": {
            state.title(): LANGUAGES[code]["name"] for state, code in STATE_LANGUAGES.items()
        },
    }
