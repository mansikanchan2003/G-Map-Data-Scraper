"""
The audit log: every change someone makes through the app (the standards
review, 1 Nov 2026: auditability, separation of duties).

The session middleware (main.py) writes one row for every request that
changes something (anything but GET), from the signed-in user it already
checked: who, their role, what (a label from ACTIONS), the path, whether it
went through (the status code), and what the route chose to add through
`note(request, ...)` (counts, a decision, a reason; never message text). One
place, outside the routes and outside any model, so a new route is audited
without anyone remembering to.

Phone numbers in paths are cut to their last four digits, so the log stays
useful after a person's data is erased. Rows are never edited or deleted
(a Postgres trigger refuses it).
"""
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from src.models.audit import AuditEntry

logger = logging.getLogger("gmap_scraper.audit")

# Not worth a row: reading a chat, a typing-speed stream of inbox messages
# (each is kept in the thread with who sent it), signing out.
SKIP = (
    re.compile(r"^/api/v1/inbox/conversations/[^/]+/read$"),
    re.compile(r"^/api/v1/auth/logout$"),
    re.compile(r"^/api/v1/whatsapp/(audience/(summary|preview)|contacts/validate)$"),
    re.compile(r"^/api/v1/whatsapp/insights/(ask|snapshot)$"),
)

# (method, path pattern, label). The first match names the action.
ACTIONS = [
    ("POST", r"^/api/v1/whatsapp/campaigns$", "Launched a campaign"),
    ("POST", r"^/api/v1/whatsapp/campaigns/[^/]+/approve$", "Approved a campaign"),
    ("POST", r"^/api/v1/whatsapp/campaigns/[^/]+/reject$", "Rejected a campaign"),
    ("POST", r"^/api/v1/whatsapp/campaigns/[^/]+/cancel$", "Cancelled a campaign"),
    ("POST", r"^/api/v1/whatsapp/campaigns/[^/]+/resume$", "Resumed a campaign"),
    ("POST", r"^/api/v1/whatsapp/templates$", "Created a template"),
    ("POST", r"^/api/v1/whatsapp/templates/[^/]+/submit$", "Submitted a template to Meta"),
    ("DELETE", r"^/api/v1/whatsapp/templates/[^/]+$", "Deleted a template"),
    ("POST", r"^/api/v1/whatsapp/accounts", "Connected a WhatsApp account"),
    ("POST", r"^/api/v1/whatsapp/studio/drafts/[^/]+/approve$", "Approved a Studio draft for Meta"),
    ("POST", r"^/api/v1/whatsapp/studio/drafts/[^/]+/reject$", "Rejected a Studio draft"),
    ("POST", r"^/api/v1/whatsapp/studio/(generate|business-drafts|from-messages)$", "Asked an agent for drafts"),
    ("PUT", r"^/api/v1/agents/controls/", "Switched an agent control"),
    ("POST", r"^/api/v1/agents/learning/[^/]+/(accept|dismiss|undo)$", "Decided on a learning patch"),
    ("PUT", r"^/api/v1/agents/retention$", "Set the retention policy"),
    ("POST", r"^/api/v1/agents/retention/clean$", "Cleaned up personal data"),
    ("POST", r"^/api/v1/inbox/conversations/[^/]+/erase$", "Erased a person's data"),
    ("POST", r"^/api/v1/inbox/conversations/[^/]+/opt-out$", "Put a number on the do-not-message list"),
    ("DELETE", r"^/api/v1/inbox/conversations/[^/]+/opt-out$", "Took a number off the do-not-message list"),
    ("POST", r"^/api/v1/inbox/conversations/[^/]+/disposition$", "Recorded a disposition"),
    ("POST", r"^/api/v1/inbox/conversations/[^/]+/handover$", "Handed a chat over"),
    ("POST", r"^/api/v1/inbox/conversations/[^/]+/bot$", "Paused or resumed the bot in a chat"),
    ("POST", r"^/api/v1/inbox/conversations/[^/]+/messages$", "Sent a message"),
    ("POST", r"^/api/v1/inbox/conversations/[^/]+/media$", "Sent a file"),
    ("POST", r"^/api/v1/inbox/conversations/[^/]+/drive$", "Saved documents to Drive"),
    ("PUT", r"^/api/v1/inbox/bot-settings$", "Changed the bot's settings"),
    ("POST", r"^/api/v1/inbox/faq/teach$", "Taught the bot an FAQ question"),
    ("DELETE", r"^/api/v1/inbox/faq/teach$", "Removed a taught FAQ question"),
    ("POST", r"^/api/v1/inbox/dispositions/nudge-templates/", "Submitted nudge templates to Meta"),
    ("POST", r"^/api/v1/auth/login$", "Signed in"),
    ("POST", r"^/api/v1/auth/users/[^/]+/approve$", "Approved a user"),
    ("POST", r"^/api/v1/auth/users/[^/]+/revoke$", "Revoked a user"),
    ("POST", r"^/api/v1/auth/users/[^/]+/reject$", "Rejected a user"),
    ("PUT", r"^/api/v1/auth/users/[^/]+/", "Changed a user's access"),
    ("POST", r"^/api/v1/auth/change-password$", "Changed their password"),
    ("PUT", r"^/api/v1/whatsapp/insights/revenue-goal$", "Set the revenue goal"),
    ("PUT", r"^/api/v1/discovery/autopilot$", "Changed the scraping autopilot"),
    ("POST", r"^/api/v1/discovery/", "Started or stopped scraping"),
    ("DELETE", r"^/api/v1/applications/", "Removed an application or comment"),
]
_ACTIONS = [(m, re.compile(p), label) for m, p, label in ACTIONS]
_PHONE = re.compile(r"\+?\d{10,15}")


def masked(path: str) -> str:
    return _PHONE.sub(lambda m: "…" + m.group(0)[-4:], path)[:300]


def label(method: str, path: str) -> str:
    for m, pattern, text in _ACTIONS:
        if m == method and pattern.search(path):
            return text
    return f"{method} {masked(path)}"[:120]


def wanted(method: str, path: str) -> bool:
    return method not in ("GET", "HEAD", "OPTIONS") and path.startswith("/api/") and \
        not any(p.search(path) for p in SKIP)


def note(request, **detail) -> None:
    """Add to this request's audit row: counts, a decision, a reason. Never message text or documents."""
    try:
        current = getattr(request.state, "audit", None) or {}
        request.state.audit = {**current, **detail}
    except Exception:
        pass


def record(db: Session, actor: str, role: Optional[str], method: str, path: str, status: int,
           detail: Optional[dict] = None) -> None:
    db.add(AuditEntry(actor=actor, role=role, action=label(method, path), method=method, path=masked(path),
                      status=status, detail=detail or None))


# The middleware's sessions; tests point it at their own database.
session_factory = None


def write(user, method: str, path: str, status: int, detail: Optional[dict]) -> None:
    """The middleware's write, in its own session; a failure is logged and never fails the request."""
    from src.database import SessionLocal
    db = (session_factory or SessionLocal)()
    try:
        record(db, user.email, getattr(user, "role", None), method, path, status, detail)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"audit event=NOT_WRITTEN path={masked(path)} error={type(e).__name__}: {str(e)[:200]}")
    finally:
        db.close()


def recent(db: Session, limit: int = 200, actor: Optional[str] = None, action: Optional[str] = None) -> list:
    q = db.query(AuditEntry)
    if actor:
        q = q.filter(AuditEntry.actor == actor)
    if action:
        q = q.filter(AuditEntry.action == action)
    rows = q.order_by(AuditEntry.id.desc()).limit(max(1, min(limit, 1000))).all()
    return [{"id": r.id, "at": r.at.isoformat() if r.at else None, "actor": r.actor, "role": r.role,
             "action": r.action, "method": r.method, "path": r.path, "status": r.status, "ok": r.status < 400,
             "detail": r.detail} for r in rows]
