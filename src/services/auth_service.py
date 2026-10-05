"""
Passwords, tokens, and who is allowed in.

Access is granted in two steps that are deliberately separate: the email
domain decides who may *ask*, and an admin decides who actually gets in. A
domain check alone would let anyone at the company send messages from the
company's WhatsApp number.
"""
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from sqlalchemy.orm import Session

from src.models import User

logger = logging.getLogger("gmap_scraper.auth")

ALLOWED_DOMAIN = "eko.co.in"
# The first admin. Seeded on startup so there is someone able to approve the
# very first signup — an approval queue with nobody to read it is a deadlock.
BOOTSTRAP_ADMIN = "mansi.kanchan.intern@eko.co.in"

# What an admin can make someone when approving them.
#   member             sees the dashboard, business data, templates,
#                      campaign history and insights, and can change nothing.
#                      It is what a request gets unless more is given, so
#                      the least access is the default.
#   operator, manager  see every tab except Access Requests, and can act;
#                      they differ only in the tag they carry.
# "admin" is deliberately absent: the approvals queue belongs to the bootstrap
# admin alone, and nothing in the app can hand it to anyone else.
GRANTABLE_ROLES = ("member", "manager", "operator")

# Roles that may only look. Enforced on every request, not by hiding buttons.
READ_ONLY_ROLES = ("member",)
# Requests a read-only role may make that are not GETs: each of these only
# works something out and stores nothing.
READ_ONLY_SAFE_POSTS = (
    "/api/v1/auth/logout",
    "/api/v1/whatsapp/audience/summary",
    "/api/v1/whatsapp/audience/preview",
    "/api/v1/whatsapp/contacts/validate",
)


def may_make_request(user: "User", method: str, path: str) -> bool:
    """Whether this user's role allows the request at all."""
    if user.role not in READ_ONLY_ROLES:
        return True
    if method.upper() in ("GET", "HEAD", "OPTIONS"):
        return True
    return path in READ_ONLY_SAFE_POSTS

TOKEN_TTL_HOURS = 12
COOKIE_NAME = "autogmap_session"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def jwt_secret() -> str:
    """
    The key sessions are signed with.

    Falls back to the database password so a deployment that forgot to set it
    still signs with something private rather than a constant everyone knows.
    """
    return (
        os.environ.get("AUTH_JWT_SECRET")
        or os.environ.get("POSTGRES_PASSWORD")
        or "autogmap-dev-only-secret"
    )


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def email_is_allowed(email: str) -> bool:
    email = normalise_email(email)
    if not EMAIL_RE.match(email):
        return False
    # Guards against "someone@evil-eko.co.in.attacker.com" as well as a bare
    # suffix match like "notekо.co.in".
    return email.endswith("@" + ALLOWED_DOMAIN)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # A malformed stored hash must read as "wrong password", never as an
        # exception that the caller might treat as success.
        return False


def password_problem(password: str) -> Optional[str]:
    """Returns why a password is unacceptable, or None if it is fine."""
    if not password or len(password) < 10:
        return "Password must be at least 10 characters."
    if password.isdigit() or password.isalpha():
        return "Password must mix letters with numbers or symbols."
    return None


# A forgotten-password code: six digits, emailed to the administrator, who
# passes it to the person if the request is genuine. The administrator's say
# is the proof; nothing reaches the person asking unless it is given.
RESET_CODE_TTL_MINUTES = 10
# Wrong guesses allowed before the code is thrown away. Five tries at a
# six-digit code is a one-in-200,000 chance; unlimited tries is a certainty.
RESET_CODE_MAX_ATTEMPTS = 5
# The shortest wait before another code is sent to the same address, so the
# form cannot be used to flood someone's inbox.
RESET_CODE_RESEND_SECONDS = 60


def _reset_code_hash(user: User, code: str) -> str:
    import hashlib
    import hmac
    return hmac.new(jwt_secret().encode("utf-8"), f"{user.user_id}:{code}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _as_utc(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


def may_reset_password(user: Optional[User]) -> bool:
    """An account someone has been let into, or is waiting to be."""
    return bool(user) and user.status in ("APPROVED", "PENDING")


def start_password_reset(db: Session, user: User) -> Optional[str]:
    """
    Makes a new code for the account and returns it, to be emailed. Returns
    None when one was sent too recently to send another.
    """
    import secrets

    now = datetime.now(timezone.utc)
    sent = _as_utc(user.reset_code_sent_at)
    if sent and (now - sent).total_seconds() < RESET_CODE_RESEND_SECONDS:
        return None
    code = f"{secrets.randbelow(1_000_000):06d}"
    user.reset_code_hash = _reset_code_hash(user, code)
    user.reset_code_sent_at = now
    user.reset_code_attempts = 0
    db.commit()
    return code


def finish_password_reset(db: Session, user: Optional[User], code: str, new_password: str) -> bool:
    """
    Sets the new password if the code is the one sent, in time, and has not
    been guessed at too often. True when the password was changed.
    """
    import hmac

    if not may_reset_password(user) or not user.reset_code_hash:
        return False
    now = datetime.now(timezone.utc)
    sent = _as_utc(user.reset_code_sent_at)
    expired = not sent or (now - sent) > timedelta(minutes=RESET_CODE_TTL_MINUTES)
    if expired or (user.reset_code_attempts or 0) >= RESET_CODE_MAX_ATTEMPTS:
        user.reset_code_hash = None
        db.commit()
        return False

    given = _reset_code_hash(user, (code or "").strip())
    if not hmac.compare_digest(given, user.reset_code_hash):
        user.reset_code_attempts = (user.reset_code_attempts or 0) + 1
        if user.reset_code_attempts >= RESET_CODE_MAX_ATTEMPTS:
            user.reset_code_hash = None
        db.commit()
        return False

    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    user.reset_code_hash = None
    user.reset_code_attempts = 0
    db.commit()
    return True


def issue_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user.user_id,
            "email": user.email,
            "role": user.role,
            "iat": now,
            "exp": now + timedelta(hours=TOKEN_TTL_HOURS),
        },
        jwt_secret(),
        algorithm="HS256",
    )


def read_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def user_from_token(db: Session, token: str) -> Optional[User]:
    """
    Resolves a token to a live user.

    The database is consulted rather than trusting the token's claims, so
    revoking someone takes effect on their next request instead of whenever
    their token happens to expire.
    """
    payload = read_token(token)
    if not payload:
        return None
    user = db.query(User).filter(User.user_id == payload.get("sub")).first()
    if not user or user.status != "APPROVED":
        return None
    # A session from before the password was changed belongs to the old
    # password. Whole seconds on both sides: a token's issue time has no
    # finer grain, and signing in within the same second must still work.
    changed = user.password_changed_at
    if changed is not None:
        if changed.tzinfo is None:
            changed = changed.replace(tzinfo=timezone.utc)
        if int(payload.get("iat") or 0) < int(changed.timestamp()):
            return None
    return user


def ensure_bootstrap_admin(db: Session) -> None:
    """
    Makes sure the first admin exists and is approved.

    Called at startup. If the account was created by signing up, it is
    promoted rather than duplicated; a password it already has is never
    touched.

    Its first password comes from BOOTSTRAP_ADMIN_PASSWORD, never from the
    signup form. Signup checks only that an address is on the domain, not
    that the person typing it owns the mailbox, so letting signup set this
    account's password handed admin to whoever submitted the form first.
    Whoever can set server configuration is already trusted with the app.
    """
    existing = db.query(User).filter(User.email == BOOTSTRAP_ADMIN).first()
    if existing is None:
        existing = User(
            user_id=uuid.uuid4().hex,
            email=BOOTSTRAP_ADMIN,
            full_name="Mansi Kanchan",
            password_hash="!",            # no bcrypt hash can equal this
            role="admin",
            status="APPROVED",
        )
        db.add(existing)
        db.commit()
        logger.info(f"auth event=BOOTSTRAP_ADMIN_CREATED email={BOOTSTRAP_ADMIN}")

    changed = False
    if existing.role != "admin":
        existing.role, changed = "admin", True
    if existing.status != "APPROVED":
        existing.status, changed = "APPROVED", True
    if changed:
        logger.info(f"auth event=BOOTSTRAP_ADMIN_PROMOTED email={BOOTSTRAP_ADMIN}")

    if not has_usable_password(existing):
        initial = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD") or ""
        problem = password_problem(initial) if initial else None
        if initial and not problem:
            existing.password_hash = hash_password(initial)
            changed = True
            logger.info(f"auth event=BOOTSTRAP_ADMIN_PASSWORD_SET email={BOOTSTRAP_ADMIN}")
        else:
            logger.warning(
                f"auth event=BOOTSTRAP_ADMIN_HAS_NO_PASSWORD email={BOOTSTRAP_ADMIN} "
                + (f"reason={problem!r}" if problem else
                   "set BOOTSTRAP_ADMIN_PASSWORD and restart to enable sign-in")
            )

    if changed:
        db.commit()


def has_usable_password(user: User) -> bool:
    return bool(user.password_hash) and user.password_hash != "!"
