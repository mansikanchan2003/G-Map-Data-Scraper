"""
Sign up, sign in, and the approvals queue.

Signing up records a request; it does not create access. Only an admin moves
an account to APPROVED, and only then can it sign in.
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import User
from src.services import auth_service as auth
from src.services import notifier

logger = logging.getLogger("gmap_scraper.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class SignupRequest(BaseModel):
    email: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)
    full_name: Optional[str] = Field(None, max_length=200)
    # The role being asked for: member, manager or operator. It is a request,
    # shown to the administrator, who can give a different one on approval.
    role: Optional[str] = Field(None, max_length=20)


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)


class ChangePasswordRequest(BaseModel):
    email: str = Field(..., max_length=200)
    current_password: str = Field(..., max_length=200)
    new_password: str = Field(..., max_length=200)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., max_length=200)


class ResetPasswordRequest(BaseModel):
    email: str = Field(..., max_length=200)
    code: str = Field(..., max_length=12)
    new_password: str = Field(..., max_length=200)


class UserResponse(BaseModel):
    user_id: str
    email: str
    full_name: Optional[str] = None
    role: str
    status: str
    created_at: datetime
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ApproveRequest(BaseModel):
    # The role to give: "member" or "manager". Left out, the account keeps
    # the role it has, which for a new request is member.
    role: Optional[str] = None


class RejectRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


# --------------------------------------------------------------------------
# Dependencies
# --------------------------------------------------------------------------

def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(auth.COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in")
    user = auth.user_from_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or account no longer active")
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    return user


def _public_app_url() -> str:
    return (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/") or "http://localhost:5173"


def _set_session_cookie(response: Response, token: str) -> None:
    # httponly keeps the token out of reach of page scripts; secure follows
    # the deployment, since a Secure cookie is dropped over plain http in dev.
    https = _public_app_url().startswith("https://")
    response.set_cookie(
        auth.COOKIE_NAME, token,
        httponly=True,
        secure=https,
        samesite="lax",
        max_age=auth.TOKEN_TTL_HOURS * 3600,
        path="/",
    )


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@router.post("/signup", status_code=201)
def signup(payload: SignupRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Records a request for access. It does not sign anyone in.

    The domain check decides who may ask; an admin decides who gets in.
    """
    email = auth.normalise_email(payload.email)

    if not auth.email_is_allowed(email):
        raise HTTPException(
            status_code=400,
            detail=f"Only @{auth.ALLOWED_DOMAIN} addresses can request access.",
        )

    problem = auth.password_problem(payload.password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    role = (payload.role or "member").strip().lower()
    if role not in auth.GRANTABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role must be one of: {', '.join(auth.GRANTABLE_ROLES)}.",
        )

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        # The seeded admin is never claimed from here, even while it has no
        # password: nothing proves the person submitting this owns the
        # mailbox. Its password comes from BOOTSTRAP_ADMIN_PASSWORD.
        if existing.status == "PENDING":
            raise HTTPException(status_code=409, detail="A request for this address is already awaiting approval.")
        if existing.status == "REJECTED":
            raise HTTPException(status_code=403, detail="This address was declined. Contact the administrator.")
        raise HTTPException(status_code=409, detail="An account already exists for this address.")

    user = User(
        user_id=uuid.uuid4().hex,
        email=email,
        full_name=(payload.full_name or "").strip() or None,
        password_hash=auth.hash_password(payload.password),
        # Held on a PENDING account, which cannot sign in: it takes effect
        # only if the administrator approves it as asked.
        role=role,
        status="PENDING",
    )
    db.add(user)
    db.commit()
    logger.info(f"auth event=SIGNUP_REQUESTED email={email}")

    # Sent in the background: a slow or broken mail server must not make the
    # signup itself fail, and the request is already safely recorded.
    background.add_task(
        notifier.notify_signup_request,
        auth.BOOTSTRAP_ADMIN, email, user.full_name,
        f"{_public_app_url()}/#approvals",
    )

    return {"status": "PENDING", "email": email,
            "message": "Request sent. You can sign in once an administrator approves it."}


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    email = auth.normalise_email(payload.email)
    user = db.query(User).filter(User.email == email).first()

    # One message for "no such account" and "wrong password", so the form
    # cannot be used to find out which addresses exist.
    invalid = HTTPException(status_code=401, detail="Incorrect email or password.")
    if not user or not auth.has_usable_password(user):
        raise invalid
    if not auth.verify_password(payload.password, user.password_hash):
        raise invalid

    if user.status == "PENDING":
        raise HTTPException(status_code=403, detail="Your account is still waiting for approval.")
    if user.status == "REJECTED":
        raise HTTPException(status_code=403, detail="This account was declined.")
    if user.status != "APPROVED":
        raise HTTPException(status_code=403, detail="This account is not active.")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    _set_session_cookie(response, auth.issue_token(user))
    logger.info(f"auth event=LOGIN email={email} role={user.role}")
    return UserResponse.model_validate(user)


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Emails a six-digit code for the account to the administrator.

    Not to the person asking: the administrator decides whether the request
    is genuine and passes the code on. The answer is the same whether or not
    the address has an account, so this cannot be used to find out which do.
    """
    if not notifier.smtp_configured():
        # True for every address alike, so it gives nothing away.
        raise HTTPException(
            status_code=503,
            detail="Password reset by email is not set up on this server. Ask the administrator.",
        )

    email = auth.normalise_email(payload.email)
    user = db.query(User).filter(User.email == email).first()
    if auth.may_reset_password(user):
        code = auth.start_password_reset(db, user)
        if code:
            sent = notifier.send_reset_code(auth.BOOTSTRAP_ADMIN, email, code,
                                            auth.RESET_CODE_TTL_MINUTES)
            logger.info(f"auth event=RESET_CODE_SENT email={email} delivered={sent}")
        else:
            logger.info(f"auth event=RESET_CODE_THROTTLED email={email}")

    return {
        "status": "sent",
        "message": f"If {email} has an account, a 6-digit code has been emailed to the "
                   f"administrator ({auth.BOOTSTRAP_ADMIN}). Ask them for it; it works for "
                   f"{auth.RESET_CODE_TTL_MINUTES} minutes.",
    }


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, response: Response, db: Session = Depends(get_db)):
    """Sets a new password for whoever holds the code that was emailed."""
    problem = auth.password_problem(payload.new_password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    email = auth.normalise_email(payload.email)
    user = db.query(User).filter(User.email == email).first()
    if not auth.finish_password_reset(db, user, payload.code, payload.new_password):
        raise HTTPException(
            status_code=400,
            detail="That code is incorrect or has expired. Ask for a new one and try again.",
        )
    logger.info(f"auth event=PASSWORD_RESET email={email}")
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"status": "changed", "message": "Password changed. Sign in with the new one."}


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, response: Response, db: Session = Depends(get_db)):
    """
    Changes a password for whoever can give the current one.

    The current password is the proof of ownership, so this works signed in
    or not, and for every role. It is no help with a forgotten password:
    nothing here can be done without the old one.
    """
    email = auth.normalise_email(payload.email)
    user = db.query(User).filter(User.email == email).first()

    # The same answer for an unknown address and a wrong password, as on
    # sign-in, so this cannot be used to find out which addresses exist.
    invalid = HTTPException(status_code=401, detail="Incorrect email or current password.")
    if not user or not auth.has_usable_password(user):
        raise invalid
    if not auth.verify_password(payload.current_password, user.password_hash):
        raise invalid

    problem = auth.password_problem(payload.new_password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="The new password must be different from the current one.")

    user.password_hash = auth.hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(f"auth event=PASSWORD_CHANGED email={email}")

    # Every session issued before now has just stopped working, this
    # browser's included, so its cookie is cleared rather than left to fail.
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"status": "changed", "message": "Password changed. Sign in with the new one."}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"status": "signed out"}


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)):
    return user


@router.get("/users", response_model=List[UserResponse])
def list_users(status: Optional[str] = None, _: User = Depends(current_admin),
               db: Session = Depends(get_db)):
    query = db.query(User)
    if status:
        query = query.filter(User.status == status.upper())
    return query.order_by(User.created_at.desc()).all()


@router.post("/users/{user_id}/approve", response_model=UserResponse)
def approve_user(user_id: str, background: BackgroundTasks, payload: ApproveRequest = None,
                 admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """
    Lets someone in, as a member or a manager. Called again on an account
    that is already approved, it changes the role.
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="No such user")

    role = ((payload.role if payload else None) or "").strip().lower() or None
    if role is not None:
        if role not in auth.GRANTABLE_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Role must be one of: {', '.join(auth.GRANTABLE_ROLES)}.",
            )
        if user.role == "admin":
            raise HTTPException(status_code=400, detail="The administrator's role cannot be changed.")
        user.role = role

    already = user.status == "APPROVED"
    user.status = "APPROVED"
    user.decided_by = admin.email
    user.decided_at = datetime.now(timezone.utc)
    user.rejection_reason = None
    db.commit()
    db.refresh(user)
    logger.info(f"auth event=USER_APPROVED email={user.email} role={user.role} by={admin.email}")

    # Someone already let in is not told again when only their role changes.
    if not already:
        background.add_task(notifier.notify_decision, user.email, True, _public_app_url())
    return user


@router.post("/users/{user_id}/revoke", response_model=UserResponse)
def revoke_user(user_id: str, admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    """
    Takes access away from someone who had it. Their next request is
    refused, since every request looks the account up afresh; approving
    them again restores it.
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="No such user")
    if user.user_id == admin.user_id or user.role == "admin":
        raise HTTPException(status_code=400, detail="The administrator's access cannot be removed.")

    user.status = "DISABLED"
    user.decided_by = admin.email
    user.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    logger.info(f"auth event=USER_REVOKED email={user.email} by={admin.email}")
    return user


@router.post("/users/{user_id}/reject", response_model=UserResponse)
def reject_user(user_id: str, payload: RejectRequest, background: BackgroundTasks,
                admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="No such user")
    if user.user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="You cannot decline your own account.")

    user.status = "REJECTED"
    user.decided_by = admin.email
    user.decided_at = datetime.now(timezone.utc)
    user.rejection_reason = (payload.reason or "").strip() or None
    db.commit()
    db.refresh(user)
    logger.info(f"auth event=USER_REJECTED email={user.email} by={admin.email}")

    background.add_task(notifier.notify_decision, user.email, False,
                        _public_app_url(), user.rejection_reason)
    return user
