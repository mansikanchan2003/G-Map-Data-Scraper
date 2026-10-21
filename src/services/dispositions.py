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
    # The lead's stage moves on (Move to CAT 1).
    stage: Optional[str] = None


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    # The colour family in the inbox and the Dispositions tab.
    group: str
    icon: str
    subs: List[Sub] = field(default_factory=list)


def _visit_task() -> Step:
    return Step("visit_planned", NOW, DC, TASK, cancel_on_reply=False,
                task="Assign to the District Coordinator and schedule the visit; the DC reports to Eko")


CATEGORIES: List[Category] = [
    Category("interested", "Interested", "positive", "thumb_up", [
        Sub("int_visit", "Physical visit required", "interested",
            "Assign to DC, schedule visit, DC will give report to Eko", "DCs",
            (_visit_task(), Step("visit_planned", NOW, BOT, NUDGE))),
        Sub("int_ready", "Ready to proceed", "interested", "Move to CAT 1", "DCs/Bot",
            (Step("next_steps", NOW, BOT, NUDGE),), stage="CAT 1"),
        Sub("int_more_info", "More information required", "interested", "Call", "Human",
            (Step("more_info", NOW, HUMAN, CALL, expects_reply=True),)),
        Sub("int_callback", "Callback requested", "interested",
            "Call & WhatsApp notification for call back confirmation", "Bot",
            (Step("callback_confirm", NOW, BOT, NUDGE),
             Step("callback_due", AT_TIME, BOT, CALL, expects_reply=True, cancel_on_reply=False)), asks="time"),
        Sub("int_docs_pending", "Documents pending", "interested", "Follow up by calls & notifications", "DCs/Bot",
            (Step("docs_reminder", NOW, BOT, NUDGE),
             Step("docs_reminder", IN_2_DAYS, BOT, CALL, expects_reply=True))),
        # Not in the sheet: what the bot records itself once documents arrive.
        Sub("int_submitted", "Documents submitted", "interested", "Move to CAT 1", "Bot", stage="CAT 1"),
    ]),
    Category("not_interested", "Not Interested", "negative", "thumb_down", [
        Sub("ni_investment", "Investment issue", "not_interested", "Connect for BT proposal", "Human",
            (Step("lower_investment", NOW, HUMAN, CALL, expects_reply=True),)),
        Sub("ni_mistake", "Applied by mistake", "not_interested", "", "", closes=True),
        Sub("ni_no_requirement", "No requirement", "not_interested", "", "", closes=True),
        Sub("ni_currently", "Not interested currently", "not_interested", "", "", closes=True),
    ]),
    Category("rejected", "Rejected", "negative", "block", [
        Sub("rej_bm", "BM not agree", "rejected", "Connect for other bank proposal", "Human",
            (Step("other_bank", NOW, HUMAN, CALL, expects_reply=True),)),
        Sub("rej_credit", "Low credit score", "rejected", "Connect for BT/other proposal", "Bot - Human",
            (Step("lower_investment", NOW, BOT, CALL, expects_reply=True),)),
        Sub("rej_eligibility", "Eligibility criteria not met", "rejected", "Connect for BT/other proposal", "Bot - Human",
            (Step("lower_investment", NOW, BOT, CALL, expects_reply=True),)),
        # Not in the sheet: the bot's own outcome for a PIN code Eko does not serve.
        Sub("rej_outside_area", "Outside our service area", "rejected", "", "Bot", closes=True),
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
        Sub("inv_wrong_number", "Wrong number", "invalid", "Mark as bogus lead", "Bot", closes=True),
        Sub("inv_invalid_number", "Invalid number", "invalid", "Mark as bogus lead", "Bot", closes=True),
        Sub("inv_denied", "Person denied applying", "invalid", "Convince for BT", "Human",
            (Step("lower_investment", NOW, HUMAN, CALL, expects_reply=True),)),
        Sub("inv_incorrect", "Incorrect customer details", "invalid", "Mark as bogus lead", "Bot", closes=True),
    ]),
    Category("duplicate", "Duplicate / Existing", "other", "content_copy", [
        Sub("dup_lead", "Duplicate lead", "duplicate", "Map to existing lead/customer or close duplicate", "Bot", closes=True),
        Sub("dup_in_process", "Already in process", "duplicate", "Map to existing lead/customer or close duplicate", "Bot", closes=True),
        Sub("dup_existing", "Existing customer / existing CSP", "duplicate",
            "Map to existing lead/customer or close duplicate", "Bot", closes=True),
    ]),
    Category("not_decision_maker", "Not Decision Maker", "follow_up", "groups", [
        Sub("ndm_not_applicant", "Person contacted is not applicant", "not_decision_maker",
            "Obtain correct contact / schedule callback with decision maker", "Bot & Human",
            (Step("decision_maker", NOW, BOT, CALL, expects_reply=True),)),
        Sub("ndm_unavailable", "Decision maker not available", "not_decision_maker",
            "Obtain correct contact / schedule callback with decision maker", "Bot & Human",
            (Step("decision_maker", NOW, BOT, CALL, expects_reply=True),)),
    ]),
    Category("hold", "Hold / Future Prospect", "follow_up", "event_upcoming", [
        Sub("hold_later", "Interested later", "hold", "Put lead on hold and schedule follow-up date", "Bot & Human",
            (Step("checking_in", ON_DATE, BOT, CALL, expects_reply=True, cancel_on_reply=False),), asks="date"),
        Sub("hold_financial", "Financial constraint currently", "hold", "Connect for BT/other proposal", "Bot & Human",
            (Step("lower_investment", NOW, BOT, CALL, expects_reply=True),
             Step("checking_in", ON_DATE, BOT, CALL, expects_reply=True, cancel_on_reply=False)), asks="date"),
        Sub("hold_after_date", "Wants to proceed after certain date", "hold", "Connect for BT/other proposal", "Bot & Human",
            (Step("checking_in", ON_DATE, BOT, CALL, expects_reply=True, cancel_on_reply=False),), asks="date"),
        Sub("hold_no_replacement", "Replacement not available in current AO", "hold", "Connect for BT/other proposal",
            "Bot & Human",
            (Step("lower_investment", NOW, BOT, CALL, expects_reply=True),
             Step("checking_in", ON_DATE, BOT, CALL, expects_reply=True, cancel_on_reply=False)), asks="date"),
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
    "interested": "int_ready",
    "docs_pending": "int_docs_pending",
    "submitted": "int_submitted",
    "guidance": "int_more_info",
    "query_answered": "int_more_info",
    "call_back": "busy_later",
    "not_reachable": "unr_not_reachable",
    "existing_csp": "dup_existing",
    "not_interested": "ni_currently",
    "cannot_invest": "ni_investment",
    "not_eligible": "rej_eligibility",
    "outside_area": "rej_outside_area",
    "wrong_number": "inv_wrong_number",
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


def plan_text(s: Sub) -> List[str]:
    """What happens after this disposition, in words, for the person choosing it."""
    out = []
    for st in s.steps:
        when = {NOW: "now", EOD: "this evening", NEXT_DAY: "tomorrow", AT_TIME: "at the time you set",
                ON_DATE: "on the date you set", IN_2_DAYS: "in 2 days"}[st.when]
        if st.wants == TASK:
            out.append(f"{_who(st.owner)}: {st.task}")
        else:
            out.append(f"WhatsApp nudge {when}: {st.purpose.replace('_', ' ')}"
                       + (" (a WhatsApp call once calling is on)" if st.wants == CALL else ""))
    if s.stage:
        out.append(f"Lead moves to {s.stage}")
    if s.closes:
        out.append("Closes the lead: nothing more is sent")
    return out


def options() -> List[dict]:
    """Every sub-category, grouped by category, for the inbox and the tab."""
    return [{"key": s.key, "label": s.label, "group": c.group, "category": c.key, "category_label": c.label,
             "category_icon": c.icon, "action": s.action, "owner": s.owner, "asks": s.asks,
             "plan": plan_text(s)} for c in CATEGORIES for s in c.subs]
