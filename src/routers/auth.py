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


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)


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
        role="member",
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
def approve_user(user_id: str, background: BackgroundTasks,
                 admin: User = Depends(current_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="No such user")

    user.status = "APPROVED"
    user.decided_by = admin.email
    user.decided_at = datetime.now(timezone.utc)
    user.rejection_reason = None
    db.commit()
    db.refresh(user)
    logger.info(f"auth event=USER_APPROVED email={user.email} by={admin.email}")

    background.add_task(notifier.notify_decision, user.email, True, _public_app_url())
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
