"""
The dispositions the team records, from the operations sheet "Call
Dispositions" (2026-10-21): eleven categories, each with its sub-categories,
the action that follows and who owns it.

The sheet was written for phone calls. Until calls are added, every contact
it asks for is made by a WhatsApp nudge instead: each step below says the
channel it wants ("whatsapp_call", WhatsApp's own calling) and the follow-up
engine (followups.py) uses the first channel that is ready, falling back to
a nudge (contact_channels.py). Adding calls later changes no disposition.

A step is one contact or task: what it is for (`purpose`, which picks the
nudge text), when it is due, who owns it (bot, a person, or the District
Coordinator), and whether the person is expected to answer, so that no
answer can be recorded as RNR and tried again the next day, as the sheet
says for calls.

AutoGMap's part ends with "Physical visit required": once someone has
uploaded their documents, Eko Acquisition takes the lead over (assigns the
District Coordinator, the visit, onboarding). So that disposition hands over
and sets nothing in motion here. "Ready to proceed / Move to CAT 1" and
"BM not agree / connect for other bank proposal" are Eko Acquisition's own
steps, after the bank has the application, and are not AutoGMap's (the
user, 2026-10-21).

Keys used before this sheet are still read (LEGACY), so earlier outcomes in
the history keep their meaning.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# When a step is due.
NOW, EOD, NEXT_DAY, AT_TIME, ON_DATE, IN_2_DAYS = "now", "eod", "next_day", "at_time", "on_date", "in_2_days"
# Who owns a step.
BOT, HUMAN, DC = "bot", "human", "dc"
# What the sheet asks for, as a channel; contact_channels decides what is used.
CALL, NUDGE, TASK = "whatsapp_call", "whatsapp_nudge", "task"
# Who takes a lead over when AutoGMap's part is done, and how it reaches them.
HANDED_TO = "Eko Acquisition"
API = "eko_acquisition_api"


@dataclass(frozen=True)
class Step:
    purpose: str
    when: str = NOW
    owner: str = BOT
    wants: str = CALL
    # No answer in a day is RNR, and the contact is tried again (calls: "reattempt next day").
    expects_reply: bool = False
    # A reply before it is due makes it unnecessary.
    cancel_on_reply: bool = True
    # For a task: what the person or DC is to do.
    task: Optional[str] = None


@dataclass(frozen=True)
class Sub:
    key: str
    label: str
    category: str
    action: str          # the sheet's action item, as written there
    owner: str           # the sheet's owner, as written there
    steps: Tuple[Step, ...] = ()
    # Asks the person recording it for a time (call back at) or a date (follow up on).
    asks: Optional[str] = None
    # Ends the chase: pending contacts are cancelled.
    closes: bool = False
    # The lead moves on to another team (handed to Eko Acquisition).
    stage: Optional[str] = None
    # Ticket and email to the team: as the sheet's "Ticket + email" column says
    # (the user's sheet, 2026-10-23); None goes by the owner naming a person.
    email: Optional[bool] = None
    # Whether the team can record it in the Inbox; the hand-over is the bot's alone.
    pickable: bool = True


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    # The colour family in the inbox and the Dispositions tab.
    group: str
    icon: str
    subs: List[Sub] = field(default_factory=list)


CATEGORIES: List[Category] = [
    Category("interested", "Interested", "positive", "thumb_up", [
        Sub("int_more_info", "More information required", "interested", "Bot will answer their questions", "Bot",
            (Step("more_info", NOW, BOT, CALL, expects_reply=True),), email=True),
        Sub("int_callback", "Callback requested", "interested",
            "Call & WhatsApp notification for call back confirmation", "Bot",
            (Step("callback_confirm", NOW, BOT, NUDGE),
             Step("callback_due", AT_TIME, BOT, CALL, expects_reply=True, cancel_on_reply=False)), asks="time"),
        Sub("int_docs_pending", "Documents pending", "interested", "Follow up by calls & notifications", "Bot",
            (Step("docs_reminder", NOW, BOT, NUDGE),
             Step("docs_reminder", IN_2_DAYS, BOT, CALL, expects_reply=True))),
        # Not in the sheet, and only ever read from the bot's step: someone who
        # tapped Interested and is still in its questions. Sets nothing in motion.
        Sub("int_in_bot_flow", "Interested: in the bot's questions", "interested", "", "Bot"),
        # Not in the sheet (23 Oct 2026): a real PIN outside our SBI branch area. The
        # journey carries on as for anyone interested; nothing extra is sent, and the
        # lead is kept with the qualified leads for another proposal (BT, HDFC...).
        Sub("int_not_sbi", "Not qualified for SBI branch code", "interested",
            "Journey continues; kept for another proposal (BT, HDFC...)", "Bot"),
        # The end of AutoGMap's journey: documents are in, and Eko Acquisition
        # takes over. The bot's own outcome once documents are uploaded.
        Sub("int_visit", "Physical visit required", "interested",
            "Assign to DC, schedule visit, DC will give report to Eko", "DCs", closes=True,
            stage=HANDED_TO, steps=(Step("acquisition_handover", NOW, BOT, API, cancel_on_reply=False),),
            # Off the team's list (the user's sheet, 2026-10-23): Eko Acquisition's step. The bot
            # still records it when the documents are uploaded, as the hand-over.
            pickable=False),
    ]),
    Category("not_interested", "Not Interested", "negative", "thumb_down", [
        Sub("ni_investment", "Investment issue", "not_interested", "Connect for BT proposal", "Bot First, then Human",
            (Step("lower_investment", NOW, BOT, CALL, expects_reply=True),), email=False),
        Sub("ni_mistake", "Applied by mistake", "not_interested", "WhatsApp message", "Bot",
            (Step("closing_polite", NOW, BOT, NUDGE),), closes=True),
        Sub("ni_no_requirement", "No requirement", "not_interested", "WhatsApp message", "Bot",
            (Step("closing_polite", NOW, BOT, NUDGE),), closes=True),
        Sub("ni_currently", "Not interested currently", "not_interested", "WhatsApp message", "Bot",
            (Step("closing_later", NOW, BOT, NUDGE),), closes=True),
    ]),
    Category("rejected", "Rejected", "negative", "block", [
        Sub("rej_credit", "Low credit score", "rejected", "Connect for BT/other proposal", "Bot",
            (Step("lower_investment", NOW, BOT, CALL, expects_reply=True),), email=True),
        Sub("rej_eligibility", "Eligibility criteria not met", "rejected", "Connect for BT/other proposal", "Bot",
            (Step("lower_investment", NOW, BOT, CALL, expects_reply=True),), email=True),
    ]),
    Category("busy", "Busy / Callback", "follow_up", "schedule", [
        Sub("busy_busy", "Busy", "busy", "Notification & calls", "Bot",
            (Step("callback_confirm", NOW, BOT, NUDGE),
             Step("callback_due", EOD, BOT, CALL, expects_reply=True, cancel_on_reply=False))),
        Sub("busy_later", "Asked to call later", "busy", "Notification & calls", "Bot",
            (Step("callback_confirm", NOW, BOT, NUDGE),
             Step("callback_due", EOD, BOT, CALL, expects_reply=True, cancel_on_reply=False))),
        Sub("busy_at_time", "Call at specific time", "busy", "Notification & calls", "Bot",
            (Step("callback_confirm", NOW, BOT, NUDGE),
             Step("callback_due", AT_TIME, BOT, CALL, expects_reply=True, cancel_on_reply=False)), asks="time"),
    ]),
    Category("rnr", "RNR", "follow_up", "phone_missed", [
        Sub("rnr_no_answer", "No answer", "rnr", "Reattempt next day & notification", "Bot",
            (Step("missed_you", NEXT_DAY, BOT, CALL, expects_reply=True),)),
        Sub("rnr_not_picked", "Ringing but not picked", "rnr", "Reattempt next day & notification", "Bot",
            (Step("missed_you", NEXT_DAY, BOT, CALL, expects_reply=True),)),
    ]),
    Category("unreachable", "Unreachable", "follow_up", "signal_disconnected", [
        Sub("unr_switched_off", "Switched off", "unreachable", "Reattempt next day & notification", "Bot",
            (Step("missed_you", NEXT_DAY, BOT, CALL, expects_reply=True),)),
        Sub("unr_no_coverage", "Out of coverage", "unreachable", "Reattempt next day & notification", "Bot",
            (Step("missed_you", NEXT_DAY, BOT, CALL, expects_reply=True),)),
        Sub("unr_not_reachable", "Number not reachable", "unreachable", "Reattempt next day & notification", "Bot",
            (Step("missed_you", NEXT_DAY, BOT, CALL, expects_reply=True),)),
    ]),
    Category("invalid", "Invalid Lead", "negative", "report", [
        # "Wrong number" and "Invalid number" are off the list (the user's sheet, 2026-10-23):
        # someone who wrote back on WhatsApp has a working number. Older records read as
        # "Incorrect customer details".
        Sub("inv_denied", "Person denied applying", "invalid", "Convince for BT", "Bot",
            (Step("lower_investment", NOW, BOT, CALL, expects_reply=True),), email=True),
        Sub("inv_incorrect", "Incorrect customer details", "invalid", "Mark as bogus lead", "Bot",
            (Step("closing_sorry", NOW, BOT, NUDGE),), closes=True),
    ]),
    Category("duplicate", "Duplicate / Existing", "other", "content_copy", [
        Sub("dup_lead", "Duplicate lead", "duplicate", "Map to existing lead/customer or close duplicate", "Bot", closes=True),
        Sub("dup_in_process", "Already in process", "duplicate", "Map to existing lead/customer or close duplicate", "Bot",
            (Step("already_with_us", NOW, BOT, NUDGE),), closes=True),
        Sub("dup_existing", "Existing customer / existing CSP", "duplicate",
            "Map to existing lead/customer or close duplicate", "Bot",
            (Step("already_with_us", NOW, BOT, NUDGE),), closes=True),
    ]),
    Category("not_decision_maker", "Not Decision Maker", "follow_up", "groups", [
        Sub("ndm_not_applicant", "Person contacted is not applicant", "not_decision_maker",
            "Obtain correct contact / schedule callback with decision maker", "Bot",
            (Step("decision_maker", NOW, BOT, CALL, expects_reply=True),), email=True),
        Sub("ndm_unavailable", "Decision maker not available", "not_decision_maker",
            "Obtain correct contact / schedule callback with decision maker", "Bot",
            (Step("decision_maker", NOW, BOT, CALL, expects_reply=True),), email=True),
    ]),
    Category("hold", "Hold / Future Prospect", "follow_up", "event_upcoming", [
        Sub("hold_later", "Interested later", "hold", "Put lead on hold and schedule follow-up date", "Bot",
            (Step("checking_in", ON_DATE, BOT, CALL, expects_reply=True, cancel_on_reply=False),), asks="date",
            email=True),
        Sub("hold_financial", "Financial constraint currently", "hold", "Connect for BT/other proposal", "Bot",
            (Step("lower_investment", NOW, BOT, CALL, expects_reply=True),
             Step("checking_in", ON_DATE, BOT, CALL, expects_reply=True, cancel_on_reply=False)), asks="date",
            email=True),
        Sub("hold_after_date", "Wants to proceed after certain date", "hold", "Connect for BT/other proposal", "Bot",
            (Step("checking_in", ON_DATE, BOT, CALL, expects_reply=True, cancel_on_reply=False),), asks="date",
            email=True),
        # "Replacement not available in current AO" is off the list (the user's sheet,
        # 2026-10-23); older records read as "Financial constraint currently".
    ]),
    Category("language", "Language Barrier", "follow_up", "translate", [
        Sub("lang_barrier", "Cannot communicate due to language mismatch", "language",
            "Reassign lead to suitable language caller", "Bot",
            (Step("choose_language", NOW, BOT, NUDGE),
             Step("choose_language", NOW, HUMAN, TASK, cancel_on_reply=False,
                  task="Reassign the lead to someone who speaks their language"))),
    ]),
    # Not in the sheet: outcomes the bot reads from a chat no campaign started.
    Category("other", "Other", "other", "more_horiz", [
        Sub("enquiry", "Enquiry, not from a campaign", "other", "", ""),
        Sub("other", "Other", "other", "", ""),
    ]),
]

SUBS: Dict[str, Sub] = {s.key: s for c in CATEGORIES for s in c.subs}
CATEGORY: Dict[str, Category] = {c.key: c for c in CATEGORIES}

# Keys recorded before the sheet, and what they are now.
LEGACY = {
    "interested": "int_in_bot_flow",
    "docs_pending": "int_docs_pending",
    "submitted": "int_visit",
    # Briefly in the sheet's first version here (21 Oct), now Eko Acquisition's.
    "int_ready": "int_in_bot_flow",
    "int_submitted": "int_visit",
    "guidance": "int_more_info",
    "query_answered": "int_more_info",
    "call_back": "busy_later",
    "not_reachable": "unr_not_reachable",
    "existing_csp": "dup_existing",
    "not_interested": "ni_currently",
    "cannot_invest": "ni_investment",
    "not_eligible": "rej_eligibility",
    # A PIN outside our SBI branch area was a rejection until 23 Oct 2026; the
    # journey carries on now, so those records read as today's disposition.
    "outside_area": "int_not_sbi",
    # Off the list since the user's sheet of 23 Oct 2026.
    "inv_wrong_number": "inv_incorrect",
    "inv_invalid_number": "inv_incorrect",
    "hold_no_replacement": "hold_financial",
    "rej_outside_area": "int_not_sbi",
    "wrong_number": "inv_incorrect",
}


def normalise(key: Optional[str]) -> Optional[str]:
    """Today's key for one recorded at any time."""
    return LEGACY.get(key, key) if key else key


def sub(key: Optional[str]) -> Optional[Sub]:
    return SUBS.get(normalise(key))


def label(key: Optional[str]) -> Optional[str]:
    s = sub(key)
    return s.label if s else None


def category_of(key: Optional[str]) -> Optional[Category]:
    s = sub(key)
    return CATEGORY[s.category] if s else None


def group(key: Optional[str]) -> str:
    c = category_of(key)
    return c.group if c else "other"


def _who(owner: str) -> str:
    return {BOT: "Bot", HUMAN: "Team", DC: "District Coordinator"}[owner]


# What each nudge does, in plain words: "a WhatsApp message now to <this>".
PURPOSE_PLAIN = {
    "more_info": "invite their questions",
    "callback_confirm": "confirm we will get back to them at their time",
    "callback_due": "get back to them, as promised",
    "docs_reminder": "remind them to upload their documents",
    "lower_investment": "offer the lower-investment option",
    "missed_you": "try them again",
    "decision_maker": "ask for the applicant's number",
    "checking_in": "check back with them",
    "choose_language": "ask which language they prefer",
    "closing_polite": "acknowledge their answer politely and close with care",
    "closing_later": "close politely, and say we are here whenever they are interested",
    "closing_sorry": "apologise for the trouble and close",
    "already_with_us": "say they are already working with us",
}
WHEN_PLAIN = {NOW: "now", EOD: "this evening", NEXT_DAY: "tomorrow morning", AT_TIME: "at the time you set",
              ON_DATE: "on the date you set", IN_2_DAYS: "2 days later"}


def plan_text(s: Sub, calls: bool = True) -> List[str]:
    """
    What happens after this disposition, in plain words. `calls` notes where
    a WhatsApp call will take over once calling is on (for the team choosing
    it; left out of a lead's journey).
    """
    out = []
    for st in s.steps:
        if st.wants == TASK:
            out.append(f"{_who(st.owner)} to do: {st.task}")
        elif st.wants == API:
            out.append(f"Sent to {HANDED_TO}")
        else:
            out.append(f"A WhatsApp message {WHEN_PLAIN[st.when]} to {PURPOSE_PLAIN.get(st.purpose, st.purpose.replace('_', ' '))}"
                       + (" (a WhatsApp call once calling is on)" if calls and st.wants == CALL else ""))
    if s.stage:
        out.append(f"Handed over to {s.stage}: AutoGMap's part ends")
    elif s.closes:
        out.append("Lead closed: nothing more is sent")
    return out


def needs_team(s: Optional[Sub]) -> bool:
    """
    Whether a person has to act on it: as the sheet's "Ticket + email" column
    says (the user's sheet, 2026-10-23), else where its owner names a human.
    These go to Kavya and Mansi as a ticket and an email; nothing else emails.
    """
    if s is None:
        return False
    if s.email is not None:
        return s.email
    return "human" in (s.owner or "").lower()


def options() -> List[dict]:
    """Every sub-category, grouped by category, for the inbox and the tab."""
    return [{"key": s.key, "label": s.label, "group": c.group, "category": c.key, "category_label": c.label,
             "category_icon": c.icon, "action": s.action, "owner": s.owner, "asks": s.asks,
             "plan": plan_text(s) + (["Ticket and email to Kavya and Mansi"] if needs_team(s) else [])}
            for c in CATEGORIES for s in c.subs if s.pickable]
