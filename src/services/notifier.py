"""
Email notifications for signup approvals.

Optional by design: with no SMTP settings the app still works and the admin
still sees the request in the approvals queue. A missing mail server must not
stop someone signing up, so every failure here is logged and swallowed.
"""
import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger("gmap_scraper.notifier")


def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_FROM"))


def _send(to: str, subject: str, body: str) -> bool:
    if not smtp_configured():
        logger.info(f"notifier event=EMAIL_SKIPPED reason=smtp_not_configured to={to}")
        return False

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    # Google displays an app password as four groups of four. Pasting it with
    # those spaces is the obvious thing to do and some servers reject it, so
    # they are stripped rather than left to fail at login time.
    password = (os.environ.get("SMTP_PASSWORD") or "").replace(" ", "") or None
    sender = os.environ["SMTP_FROM"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(body)

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            server.starttls()
        with server:
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        logger.info(f"notifier event=EMAIL_SENT to={to} subject={subject!r}")
        return True
    except Exception as e:
        # Never surfaced to the person signing up: their request was recorded,
        # and the admin can see it in the queue regardless.
        logger.error(f"notifier event=EMAIL_FAILED to={to} error={e}")
        return False


def notify_signup_request(admin_email: str, applicant_email: str,
                          applicant_name: Optional[str], approvals_url: str) -> bool:
    name = applicant_name or applicant_email
    return _send(
        admin_email,
        f"AutoGMap: access request from {applicant_email}",
        f"{name} ({applicant_email}) has asked for access to AutoGMap.\n\n"
        f"Approve or decline here:\n{approvals_url}\n\n"
        f"They cannot sign in until you do.\n",
    )


def notify_decision(applicant_email: str, approved: bool, app_url: str,
                    reason: Optional[str] = None) -> bool:
    if approved:
        return _send(
            applicant_email,
            "AutoGMap: your access has been approved",
            f"Your AutoGMap access has been approved. You can sign in here:\n{app_url}\n",
        )
    return _send(
        applicant_email,
        "AutoGMap: your access request was declined",
        "Your request for AutoGMap access was declined."
        + (f"\n\nReason: {reason}\n" if reason else "\n"),
    )


def notify_button_click(admin_email: str, lead: dict) -> bool:
    """
    Tell the admin someone asked to be contacted.

    Sent per tap rather than batched: the point of a "Call me back" button is
    that somebody is interested right now, and a digest tomorrow is a lead
    gone cold.
    """
    def line(label, value):
        return f"{label:12} {value}" if value else None

    details = [
        line("Name", lead.get("name")),
        line("Phone", lead.get("phone")),
        line("Category", lead.get("category")),
        line("District", lead.get("district")),
        line("State", lead.get("state")),
        line("Campaign", lead.get("campaign")),
        line("Button", lead.get("button_text")),
        line("Tapped at", lead.get("clicked_at")),
    ]
    body = "\n".join(d for d in details if d)

    phone = (lead.get("phone") or "").lstrip("+")
    return _send(
        admin_email,
        f"AutoGMap: {lead.get('name') or lead.get('phone')} tapped "
        f"\u201c{lead.get('button_text') or 'a button'}\u201d",
        f"{lead.get('name') or 'A recipient'} responded to a WhatsApp campaign.\n\n"
        f"{body}\n\n"
        f"Reply on WhatsApp: https://wa.me/{phone}\n",
    )
