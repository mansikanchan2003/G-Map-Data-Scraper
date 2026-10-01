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
