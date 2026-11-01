"""
How long AutoGMap keeps a person's chat and documents, and erasing them (DPDP).

Two things, both from the standards review (1 Nov 2026):

- Retention. The admin sets how long uploaded documents are kept after they
  were submitted, and how long the chat of someone who never submitted is
  kept after its last message. The periods are for legal/compliance to
  confirm, so the policy starts switched off with none set, and nothing is
  ever due until it is on. When it is on, what is due is listed for the
  admin, and nothing goes until the admin confirms that list: a person
  approves every clean-up, and only what they were shown.

- Erasure on request. An admin erases one person's data from the Inbox, with
  the reason; their number stays on the do-not-message list.

What erasing does:
- documents: the server's copies are deleted, the Drive folder (or files) is
  moved to Drive's trash (recoverable there for 30 days), their records go,
  the upload link stops working, and what DigiLocker gave is forgotten;
- chat: every message's text is replaced with a note, media files are
  deleted, and the name and free-text notes kept about the person (ticket
  questions, team comments, disposition notes, names on campaign rows, the
  lead journey) are cleared. Counts stay, so reports and funnels still add up:
  the conversation, its stages and dispositions remain, without the person.
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from src.models.app_setting import AppSetting
from src.models.inbox import (AttentionTicket, ChatActivity, LeadJourney, LeadJourneyStep, OnboardingDocument,
                              WhatsAppConversation, WhatsAppMessage)
from src.services import inbox

logger = logging.getLogger("gmap_scraper.retention")

KEY = "retention_policy"
REMOVED = "[removed under the retention policy]"
ERASED = "[erased at the person's request]"
DOCUMENTS, CHAT, ALL = "documents", "chat", "all"
# What stays of the bot's notes: the funnel's facts, nothing that names or reaches the person.
_KEEP_BOT_DATA = {"lang", "lang_campaign", "campaign_lang", "campaign", "coverage", "education", "franchise",
                  "can_invest", "trigger", "erased"}


# --- The policy ------------------------------------------------------------------

def policy(db: Session) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == KEY).first()
    try:
        saved = json.loads(row.value) if row and row.value else {}
    except ValueError:
        saved = {}
    return {"enabled": bool(saved.get("enabled")), "documents_days": saved.get("documents_days"),
            "chat_days": saved.get("chat_days"), "basis": saved.get("basis"),
            "set_by": saved.get("set_by"), "set_at": saved.get("set_at")}


def set_policy(db: Session, by: str, enabled: bool, documents_days: Optional[int], chat_days: Optional[int],
               basis: Optional[str]) -> dict:
    """The admin's policy. Switching it on needs both periods and what they rest on (e.g. compliance's approval)."""
    if enabled and not (documents_days and chat_days and (basis or "").strip()):
        raise ValueError("To switch the clean-up on, set both periods and what they are based on "
                         "(for example: confirmed by compliance on 5 Nov).")
    value = {"enabled": bool(enabled), "documents_days": documents_days, "chat_days": chat_days,
             "basis": (basis or "").strip()[:300] or None, "set_by": by, "set_at": inbox.now().isoformat()}
    row = db.query(AppSetting).filter(AppSetting.key == KEY).first()
    if row:
        row.value = json.dumps(value)
    else:
        db.add(AppSetting(key=KEY, value=json.dumps(value)))
    db.flush()
    logger.info(f"retention event=POLICY_SET by={by} enabled={enabled} documents_days={documents_days} "
                f"chat_days={chat_days}")
    return policy(db)


# --- What is due -----------------------------------------------------------------

def _erased(conv: WhatsAppConversation, scope: str) -> bool:
    done = ((conv.bot_data or {}).get("erased") or {}).get("scope")
    return done == ALL or done == scope


def due(db: Session, now: Optional[datetime] = None) -> List[dict]:
    """What the policy says should go now: [{phone, name, scope, since, files, messages}]. Empty while it is off."""
    p = policy(db)
    if not p["enabled"] or not p["documents_days"] or not p["chat_days"]:
        return []
    now = now or inbox.now()
    out = []
    docs_before = now - timedelta(days=int(p["documents_days"]))
    for conv in db.query(WhatsAppConversation).filter(WhatsAppConversation.documents_submitted_at.isnot(None)).all():
        if inbox.aware(conv.documents_submitted_at) > docs_before:
            continue
        files = db.query(OnboardingDocument).filter(OnboardingDocument.phone == conv.phone).count()
        if files:
            out.append({"phone": conv.phone, "name": conv.profile_name, "scope": DOCUMENTS,
                        "since": inbox.aware(conv.documents_submitted_at).isoformat(), "files": files, "messages": 0})
    chats_before = now - timedelta(days=int(p["chat_days"]))
    for conv in (db.query(WhatsAppConversation)
                 .filter(WhatsAppConversation.documents_submitted_at.is_(None),
                         WhatsAppConversation.last_message_at.isnot(None)).all()):
        if inbox.aware(conv.last_message_at) > chats_before or _erased(conv, CHAT):
            continue
        n = db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == conv.phone).count()
        if n:
            out.append({"phone": conv.phone, "name": conv.profile_name, "scope": CHAT,
                        "since": inbox.aware(conv.last_message_at).isoformat(), "files": 0, "messages": n})
    return out


def clean(db: Session, items: List[dict], by: str) -> dict:
    """
    Clean up what the admin confirmed: only items they were shown that are still
    due now (approval is bound to those numbers and scopes). Returns counts.
    """
    still = {(d["phone"], d["scope"]) for d in due(db)}
    done, skipped = [], 0
    for item in items:
        key = (item.get("phone"), item.get("scope"))
        if key not in still:
            skipped += 1
            continue
        done.append(erase(db, key[0], by, "Retention policy", key[1], note=REMOVED))
    logger.info(f"retention event=CLEANED by={by} done={len(done)} skipped={skipped}")
    return {"cleaned": len(done), "skipped": skipped,
            "files": sum(d["files"] for d in done), "messages": sum(d["messages"] for d in done),
            "drive_errors": [e for d in done for e in d["drive_errors"]]}


# --- Erasing -------------------------------------------------------------------------

def _remove_file(path: Optional[str]) -> None:
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError as e:
            logger.warning(f"retention event=FILE_NOT_REMOVED error={type(e).__name__}")


def erase(db: Session, phone: str, by: str, reason: str, scope: str = ALL, note: str = ERASED) -> dict:
    """Erase this person's documents, chat, or both (see the module notes). The caller commits."""
    from src.services import drive_uploads

    conv = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == phone).first()
    if conv is None:
        raise ValueError("No conversation with this number")
    files = messages = 0
    drive_errors = []
    data = dict(conv.bot_data or {})

    if scope in (DOCUMENTS, ALL):
        docs = db.query(OnboardingDocument).filter(OnboardingDocument.phone == phone).all()
        folder = data.get("drive_folder_id")
        drive_ids = [folder] if folder else [d.drive_file_id for d in docs if d.drive_file_id]
        for drive_id in drive_ids:
            try:
                drive_uploads.trash(drive_id)
            except Exception as e:
                drive_errors.append(str(e)[:200])
                logger.warning(f"retention event=DRIVE_NOT_TRASHED phone=...{phone[-4:]} error={str(e)[:200]}")
        for d in docs:
            _remove_file(d.stored_path)
            db.delete(d)
            files += 1
        conv.drive_folder_url = None
        conv.upload_token = None
        conv.upload_token_expires_at = None
        for k in ("drive_folder_id", "digilocker"):
            data.pop(k, None)

    if scope in (CHAT, ALL):
        for m in db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == phone).all():
            _remove_file((m.payload or {}).get("stored") if isinstance(m.payload, dict) else None)
            m.body, m.payload = note, {"erased": True}
            messages += 1
        from src.models.application import ApplicationComment, QualifiedLead
        from src.models.whatsapp import WhatsAppCampaignRecipient, WhatsAppReply
        for c in db.query(ApplicationComment).filter(ApplicationComment.phone == phone).all():
            c.body = note
        for r in db.query(WhatsAppReply).filter(WhatsAppReply.phone == phone).all():
            r.body = note
        for r in db.query(WhatsAppCampaignRecipient).filter(WhatsAppCampaignRecipient.phone == phone).all():
            r.name, r.variables = None, None
        for t in db.query(AttentionTicket).filter(AttentionTicket.phone == phone).all():
            t.raised_by_name, t.question, t.latest_question, t.bot_answer = None, note, note, None
        for a in db.query(ChatActivity).filter(ChatActivity.phone == phone).all():
            a.note = None
        q = db.get(QualifiedLead, phone)
        if q is not None:
            q.name = None
        j = db.get(LeadJourney, phone)
        if j is not None:
            j.name = None
        for s in db.query(LeadJourneyStep).filter(LeadJourneyStep.phone == phone).all():
            s.detail = None
        conv.profile_name = None
        conv.disposition_note = None
        conv.attention_reason = note if conv.attention_reason else None
        data = {k: v for k, v in data.items() if k in _KEEP_BOT_DATA}

    data["erased"] = {"scope": ALL if _erased(conv, DOCUMENTS if scope == CHAT else CHAT) else scope,
                      "at": inbox.now().isoformat(), "by": by, "reason": reason[:300]}
    conv.bot_data = data
    db.add(ChatActivity(activity_id=os.urandom(16).hex(), phone=phone, kind="erased", value=scope,
                        note=reason[:500], by=by, at=inbox.now()))
    db.flush()
    logger.info(f"retention event=ERASED phone=...{phone[-4:]} scope={scope} by={by} files={files} "
                f"messages={messages} drive_errors={len(drive_errors)}")
    return {"phone": phone, "scope": scope, "files": files, "messages": messages, "drive_errors": drive_errors}
