"""
The Dashboard's missing-step alert (the user, 2026-10-22): first of all, a
lead with no disposition where one is due, and a disposition whose action
item is missing or not done; then, lower down, records that do not add up.

Missing disposition:
- the team replied, took the chat over or solved its question, and recorded
  no outcome after (2 hours' grace);
- the lead went quiet in the bot's questions days ago and nobody recorded
  what became of them (RNR, hold, not interested...).

Missing or overdue action item:
- a disposition recorded, but its action (the sheet's) never set up;
- a nudge due over an hour ago and not sent;
- a nudge waiting more than a day for Meta to approve its template;
- a task for the team or the District Coordinator open for 2 days or more;
- a question waiting for the team for more than a day;
- the hand-over to Eko Acquisition failed or still waiting.

Records that do not add up, each naming the step that is there and the one
that is missing:

- tapped a button / clicked the link / replied, but no sent message;
- delivered or read, but not sent;
- read, but not delivered (Meta's delivered update did not arrive);
- documents in, but the qualifying answers (PIN, education, ₹5 lakh) missing;
- the upload link sent without "can invest" recorded;
- an education answer with no PIN code before it;
- documents in since the hand-over began, but nothing queued for Eko Acquisition.

Nothing is changed; this only reads.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.inbox import AttentionTicket, ChatActivity, FollowUp, WhatsAppConversation, WhatsAppMessage
from src.models.whatsapp import (
    HUMAN_LINK_CLICK, WhatsAppButtonClick, WhatsAppCampaignRecipient, WhatsAppLinkClick,
)
from src.services import dispositions as dz, inbox

# The hand-over to Eko Acquisition began here; documents before it were never meant to be queued.
HANDOVER_SINCE = datetime(2026, 10, 22, tzinfo=timezone.utc)

TEAM_GRACE = timedelta(hours=2)
QUIET_FOR = timedelta(days=3)
NUDGE_LATE = timedelta(hours=1)
WAITING_TOO_LONG = timedelta(days=1)
TASK_LATE = timedelta(days=2)
TICKET_LATE = timedelta(days=1)
# Older dispositions came before their action items were set up automatically (21 Oct 2026).
ACTION_LOOKBACK = timedelta(days=14)

# check: (label, severity, group). Groups, in the order the Dashboard shows them.
GROUPS = {"disposition": "Missing disposition", "action": "Missing or overdue action item",
          "record": "Records that do not add up"}
CHECKS = {
    "no_outcome_after_team": ("The team handled the chat, but recorded no disposition", "high", "disposition"),
    "quiet_no_outcome": ("Went quiet in the bot's questions, no disposition recorded", "medium", "disposition"),
    "action_not_set_up": ("Disposition recorded, but its action item was never set up", "high", "action"),
    "nudge_overdue": ("WhatsApp message overdue: due over an hour ago, not sent", "high", "action"),
    "nudge_stuck": ("WhatsApp message waiting over a day for Meta's approval", "medium", "action"),
    "task_overdue": ("Task for the team or DC open for 2+ days", "high", "action"),
    "ticket_overdue": ("Question waiting for the team for over a day", "high", "action"),
    "handover_stuck": ("Hand-over to Eko Acquisition failed or waiting", "medium", "action"),
    "tapped_not_sent": ("Tapped a button, but no sent message", "high", "record"),
    "clicked_not_sent": ("Clicked the link, but no sent message", "high", "record"),
    "replied_not_sent": ("Replied to a campaign, but no sent message", "high", "record"),
    "delivered_not_sent": ("Delivered or read, but not sent", "high", "record"),
    "read_not_delivered": ("Read, but no delivered update", "low", "record"),
    "docs_without_answers": ("Documents in, but qualifying answers missing", "high", "record"),
    "link_without_invest": ("Upload link sent, but “can invest” not recorded", "medium", "record"),
    "education_without_pin": ("Answered education, but no PIN code before it", "medium", "record"),
    "handover_not_queued": ("Documents in, but not queued for Eko Acquisition", "high", "record"),
}


def _iso(dt) -> Optional[str]:
    dt = inbox.aware(dt)
    return dt.isoformat() if dt else None


RECORDS = ("record",)
DISPOSITIONS_AND_ACTIONS = ("disposition", "action")


def find(db: Session, groups=RECORDS) -> Dict:
    """
    Every lead with a missing step, worst first, and how many of each. Two
    Dashboard alerts read it: the missing-step alert (records, as first
    built) and the missing dispositions and action items one.
    """
    flags: List[dict] = []

    def flag(check: str, phone: str, at, detail: str, name: Optional[str] = None):
        label, severity, group = CHECKS[check]
        flags.append({"check": check, "label": label, "severity": severity, "group": group, "phone": phone,
                      "name": name, "at": _iso(at), "detail": detail})

    if any(g in groups for g in DISPOSITIONS_AND_ACTIONS):
        _dispositions_and_actions(db, flag)

    recipients = db.query(WhatsAppCampaignRecipient).all()
    by_id = {r.recipient_id: r for r in recipients}
    sent_phones = {r.phone for r in recipients if r.sent_at}
    names = {c.phone: c.profile_name for c in db.query(WhatsAppConversation.phone, WhatsAppConversation.profile_name)}

    # Campaign side: what Meta and the person did with each message.
    for r in recipients:
        nm = r.name or names.get(r.phone)
        if not r.sent_at and (r.delivered_at or r.read_at):
            flag("delivered_not_sent", r.phone, r.delivered_at or r.read_at,
                 f"Status {r.status}; Meta reported it {'read' if r.read_at else 'delivered'}, but no send time", nm)
        if r.read_at and not r.delivered_at and r.sent_at:
            flag("read_not_delivered", r.phone, r.read_at, "Read update arrived; the delivered one never did", nm)
    for rid, at in db.query(WhatsAppButtonClick.recipient_id, WhatsAppButtonClick.clicked_at).all():
        r = by_id.get(rid)
        if r is not None and not r.sent_at:
            flag("tapped_not_sent", r.phone, at, f"Recipient status {r.status}", r.name or names.get(r.phone))
    for rid, at in db.query(WhatsAppLinkClick.recipient_id, WhatsAppLinkClick.clicked_at).filter(HUMAN_LINK_CLICK).all():
        r = by_id.get(rid)
        if r is not None and not r.sent_at:
            flag("clicked_not_sent", r.phone, at, f"Recipient status {r.status}", r.name or names.get(r.phone))

    # Someone a campaign was meant for wrote back, yet no message to them was ever sent.
    unsent = {r.phone for r in recipients} - sent_phones
    if unsent:
        first_in = {}
        for phone, at in (db.query(WhatsAppMessage.phone, WhatsAppMessage.created_at)
                          .filter(WhatsAppMessage.direction == "IN", WhatsAppMessage.phone.in_(unsent)).all()):
            if phone not in first_in or inbox.aware(at) < inbox.aware(first_in[phone]):
                first_in[phone] = at
        for phone, at in first_in.items():
            flag("replied_not_sent", phone, at, "Their reply is in the inbox; the campaign row has no send time",
                 names.get(phone))

    # The bot's side: the questions must come in order.
    queued = {p for (p,) in db.query(FollowUp.phone).filter(FollowUp.wants == dz.API).distinct()}
    for c in db.query(WhatsAppConversation).all():
        data = c.bot_data or {}
        pin = (data.get("coverage") or {}).get("pincode")
        if c.documents_submitted_at:
            missing = [w for w, ok in (("PIN code", pin), ("education", data.get("education")),
                                       ("can invest", data.get("can_invest") is True)) if not ok]
            if missing:
                flag("docs_without_answers", c.phone, c.documents_submitted_at, "Missing: " + ", ".join(missing),
                     c.profile_name)
            if inbox.aware(c.documents_submitted_at) >= HANDOVER_SINCE and c.phone not in queued:
                flag("handover_not_queued", c.phone, c.documents_submitted_at,
                     "No hand-over row in follow_ups", c.profile_name)
        elif c.upload_token and data.get("can_invest") is not True:
            flag("link_without_invest", c.phone, c.bot_updated_at, f"Bot step {c.bot_step}", c.profile_name)
        if data.get("education") and not pin:
            flag("education_without_pin", c.phone, c.bot_updated_at, f"Education {data.get('education')}", c.profile_name)

    flags = [f for f in flags if f["group"] in groups]
    rank = {"high": 0, "medium": 1, "low": 2}
    order = list(GROUPS)
    flags.sort(key=lambda f: (order.index(f["group"]), rank[f["severity"]], f["at"] or ""))
    counts = Counter(f["check"] for f in flags)
    leads = defaultdict(list)
    for f in flags:
        leads[f["phone"]].append(f["check"])
    return {
        "total": len(flags),
        "leads": len(leads),
        "groups": [{"group": g, "label": label, "count": sum(1 for f in flags if f["group"] == g)}
                   for g, label in GROUPS.items() if g in groups],
        "by_check": [{"check": k, "label": CHECKS[k][0], "severity": CHECKS[k][1], "group": CHECKS[k][2],
                      "count": counts.get(k, 0)} for k in CHECKS if counts.get(k)],
        "flags": flags[:400],
    }


def _dispositions_and_actions(db: Session, flag) -> None:
    """A disposition missing where one is due, and an action item missing or not done."""
    from src.services import onboarding_bot as bot

    now = inbox.now()
    convs = {c.phone: c for c in db.query(WhatsAppConversation).all()}
    acts, fups, tix, team_msgs = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for a in db.query(ChatActivity).all():
        acts[a.phone].append(a)
    for f in db.query(FollowUp).all():
        fups[f.phone].append(f)
    for t in db.query(AttentionTicket).all():
        tix[t.phone].append(t)
    for phone, at in (db.query(WhatsAppMessage.phone, WhatsAppMessage.created_at)
                      .filter(WhatsAppMessage.direction == "OUT", WhatsAppMessage.sent_by.isnot(None),
                              WhatsAppMessage.sent_by.notin_(("bot", "campaign"))).all()):
        team_msgs[phone].append(inbox.aware(at))

    for phone, c in convs.items():
        name = c.profile_name
        records = sorted((a for a in acts[phone] if a.kind == "disposition"), key=lambda a: inbox.aware(a.at))
        by_team = [a for a in records if a.by != "bot"]
        last_team_outcome = inbox.aware(by_team[-1].at) if by_team else None

        # The team was in the chat after its last outcome (or there never was one).
        involved = list(team_msgs[phone])
        involved += [inbox.aware(a.at) for a in acts[phone] if a.kind == "to_person"]
        involved += [inbox.aware(t.resolved_at) for t in tix[phone]
                     if t.resolved_at and t.resolved_by and t.resolved_by != "bot"]
        latest = max(involved, default=None)
        if latest and now - latest >= TEAM_GRACE and (last_team_outcome is None or last_team_outcome < latest):
            flag("no_outcome_after_team", phone, latest,
                 "Last outcome recorded " + (f"before that" if last_team_outcome else "never"), name)

        # Gone quiet part-way through the bot's questions, and nobody has said what became of them.
        last_in = inbox.aware(c.last_inbound_at)
        if (c.bot_step in bot.NUDGE_STEPS and not records and not c.documents_submitted_at
                and last_in and now - last_in >= QUIET_FOR):
            flag("quiet_no_outcome", phone, last_in,
                 f"Stopped at: {bot.STEP_LABELS.get(c.bot_step, c.bot_step)}", name)

        # The last disposition's action item.
        if records:
            last = records[-1]
            s = dz.sub(last.value)
            if s and s.steps and not s.closes and now - inbox.aware(last.at) <= ACTION_LOOKBACK:
                since = inbox.aware(last.at) - timedelta(minutes=1)
                made = [f for f in fups[phone] if inbox.aware(f.created_at) >= since]
                if not made:
                    flag("action_not_set_up", phone, last.at,
                         f"{s.label}: {s.action or 'its follow-up'}", name)

        for f in fups[phone]:
            due = inbox.aware(f.due_at)
            if f.wants == dz.API:
                if f.status in ("failed",) or (f.status == "waiting" and now - inbox.aware(f.created_at) >= WAITING_TOO_LONG):
                    flag("handover_stuck", phone, f.created_at, f.note or f.status, name)
            elif f.wants == dz.TASK:
                if f.status in ("scheduled", "waiting") and now - inbox.aware(f.created_at) >= TASK_LATE:
                    flag("task_overdue", phone, f.created_at, f.task or "", name)
            elif f.status == "scheduled" and due and now - due >= NUDGE_LATE:
                flag("nudge_overdue", phone, due, dz.PURPOSE_PLAIN.get(f.purpose, f.purpose), name)
            elif f.status == "waiting" and due and now - due >= WAITING_TOO_LONG:
                flag("nudge_stuck", phone, due, dz.PURPOSE_PLAIN.get(f.purpose, f.purpose), name)

        for t in tix[phone]:
            if not t.resolved_at and now - inbox.aware(t.raised_at) >= TICKET_LATE:
                flag("ticket_overdue", phone, t.raised_at, (t.latest_question or t.question or "")[:140], name)
