"""
How a follow-up reaches someone: the ways there are, and which one is used.

The dispositions sheet asks for calls. Today the only way is a WhatsApp nudge;
WhatsApp calls (Meta's Business Calling API) are expected next (the team,
2026-10-21). Each way is a Channel with two questions, "can it reach this
person now?" and "reach them", so adding calls means writing one class and
switching it on: no disposition, rule or screen changes.

A follow-up names the channel it wants; `pick` tries that one and falls back
to a nudge, and records why a better one was skipped.

WhatsApp calling, when it comes: a business may call someone on WhatsApp only
after they have granted call permission (asked for with Meta's call
permission request message, or given by calling us first). Until it is
switched on (WHATSAPP_CALLING=on) and built, its `ready` says why not, and
every call becomes a nudge.
"""
import logging
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from src.models.inbox import FollowUp, WhatsAppConversation
from src.services import inbox, nudge_messages, nudge_templates, reply_language

logger = logging.getLogger("gmap_scraper.contact_channels")


@dataclass
class Outcome:
    ok: bool
    # Nothing could be tried yet (no approved template, calling not ready):
    # the follow-up waits rather than failing.
    waiting: bool = False
    message_id: Optional[str] = None
    language: Optional[str] = None
    error: Optional[str] = None


class Channel:
    name = ""
    label = ""

    def ready(self, db: Session, conv: WhatsAppConversation) -> Optional[str]:
        """None when this channel can reach the person now, else why not."""
        raise NotImplementedError

    def reach(self, db: Session, conv: WhatsAppConversation, f: FollowUp) -> Outcome:
        raise NotImplementedError


class WhatsAppNudge(Channel):
    """
    A WhatsApp message in the language of their last message: a plain one
    while their 24-hour window is open, else the approved template.
    """
    name, label = "whatsapp_nudge", "WhatsApp nudge"

    def ready(self, db, conv):
        return None

    def reach(self, db, conv, f):
        lang, latin = reply_language.last_reply(db, conv)
        variant = nudge_messages.variant_for(lang, latin)
        body = nudge_messages.text(f.purpose, variant)
        if inbox.window_open(conv):
            msg = inbox.send(db, conv.phone, body, sent_by="bot")
        else:
            theirs = variant
            tmpl = nudge_templates.approved(db, f.purpose, variant)
            if tmpl is None and variant != "en":
                # Their language is not approved yet; English is better than nothing.
                variant = "en"
                body = nudge_messages.text(f.purpose, variant)
                tmpl = nudge_templates.approved(db, f.purpose, variant)
            if tmpl is None:
                return Outcome(ok=False, waiting=True, language=theirs,
                               error="Their 24-hour window is shut and this nudge's template is not approved by Meta yet")
            msg = inbox.send_template(db, conv.phone, tmpl.meta_template_name, tmpl.language_code, body, sent_by="bot")
        if msg.status == "FAILED":
            return Outcome(ok=False, message_id=msg.message_id, language=variant, error=msg.error_reason)
        return Outcome(ok=True, message_id=msg.message_id, language=variant)


class WhatsAppCall(Channel):
    """
    A WhatsApp call through Meta's Business Calling API. Defined so the rest
    of the system already routes to it; not built or switched on yet.
    """
    name, label = "whatsapp_call", "WhatsApp call"

    def ready(self, db, conv):
        if os.environ.get("WHATSAPP_CALLING", "off").lower() != "on":
            return "WhatsApp calling is not switched on yet"
        if (conv.bot_data or {}).get("call_permission") != "granted":
            return "They have not given call permission"
        return "WhatsApp calling is not built yet"

    def reach(self, db, conv, f):
        return Outcome(ok=False, waiting=True, error="WhatsApp calling is not built yet")


CHANNELS = {c.name: c for c in (WhatsAppCall(), WhatsAppNudge())}
FALLBACK = "whatsapp_nudge"


def pick(db: Session, conv: WhatsAppConversation, wants: str) -> Tuple[Channel, List[str]]:
    """The channel to use for what is wanted, and why any better one was passed over."""
    skipped = []
    for name in dict.fromkeys([wants, FALLBACK]):
        channel = CHANNELS.get(name)
        if channel is None:
            continue
        why = channel.ready(db, conv)
        if why is None:
            return channel, skipped
        skipped.append(f"{channel.label}: {why}")
    return CHANNELS[FALLBACK], skipped


def status() -> List[dict]:
    """The channels and whether each is on, for the Dispositions tab."""
    calling = os.environ.get("WHATSAPP_CALLING", "off").lower() == "on"
    return [
        {"name": "whatsapp_call", "label": "WhatsApp call", "on": False,
         "note": "Planned: Meta's WhatsApp Business Calling API. Calls the sheet asks for go as WhatsApp nudges until then."
                 + (" Switched on, but not built yet." if calling else "")},
        {"name": "whatsapp_nudge", "label": "WhatsApp nudge", "on": True,
         "note": "In the language of their last message; a template once Meta approves it when their 24-hour window is shut."},
    ]
