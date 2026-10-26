import re
import threading
import time
from collections import deque
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from aura.api.deps import Viewer, optional_viewer
from aura.core import clock
from aura.core.db import write_tx
from aura.core.errors import Conflict, RateLimited, Unauthorized
from aura.core.security import (
    clear_session_cookie,
    hash_password,
    issue_session,
    needs_rehash,
    set_session_cookie,
    verify_password,
)
from aura.ledger import service as ledger
from aura.ledger.grants import activate_plan, grant_welcome
from aura.models import InvestorProfile, Startup, User, UserSession

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=200)
    name: str = Field(min_length=1, max_length=120)
    role: Literal["investor", "startup"]
    plan: Literal["scout", "angel", "syndicate"] = "scout"
    startup_name: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL.match(value):
            raise ValueError("enter a valid email address")
        return value


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_admin: bool


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name, role=user.role, is_admin=user.is_admin)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60] or "startup"


def unique_slug(s: Session, name: str) -> str:
    base = slugify(name)
    slug, n = base, 1
    while s.scalar(select(Startup.id).where(Startup.slug == slug)):
        n += 1
        slug = f"{base}-{n}"
    return slug


def create_account(s: Session, body: RegisterIn, *, is_admin: bool = False) -> User:
    if s.scalar(select(User.id).where(User.email == body.email)):
        raise Conflict("An account with this email already exists", code="EMAIL_TAKEN")
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        name=body.name.strip(),
        is_admin=is_admin,
    )
    s.add(user)
    s.flush()
    if body.role == "investor":
        s.add(InvestorProfile(user_id=user.id, plan="scout"))
        s.flush()
        grant_welcome(s, user.id)
        if body.plan != "scout":
            activate_plan(s, user, body.plan)
    else:
        name = (body.startup_name or f"{body.name}'s startup").strip()
        startup = Startup(owner_user_id=user.id, slug=unique_slug(s, name), name=name, status="draft")
        s.add(startup)
        s.flush()
        ledger.startup_wallet(s, startup.id)
    return user


# A small in-memory limiter: 10 login attempts per (ip, email) per 5 minutes.
_attempts: dict[tuple[str, str], deque[float]] = {}
_attempts_lock = threading.Lock()


def _check_rate(ip: str, email: str) -> None:
    key, now = (ip, email), time.monotonic()
    with _attempts_lock:
        window = _attempts.setdefault(key, deque())
        while window and now - window[0] > 300:
            window.popleft()
        if len(window) >= 10:
            raise RateLimited("Too many sign-in attempts — try again in a few minutes")
        window.append(now)


@router.post("/register", status_code=201, response_model=UserOut)
def register(body: RegisterIn, request: Request, response: Response) -> UserOut:
    with write_tx() as s:
        user = create_account(s, body)
        issued = issue_session(s, user, ip=request.client.host if request.client else None,
                               user_agent=request.headers.get("user-agent"))
        user.last_login_at = clock.now()
        out = _user_out(user)
    set_session_cookie(response, issued)
    return out


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response) -> UserOut:
    email = body.email.strip().lower()
    _check_rate(request.client.host if request.client else "?", email)
    with write_tx() as s:
        user = s.scalar(select(User).where(User.email == email))
        if user is None or user.status != "active" or not verify_password(user.password_hash, body.password):
            raise Unauthorized("Email or password is incorrect", code="INVALID_CREDENTIALS")
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(body.password)
        issued = issue_session(s, user, ip=request.client.host if request.client else None,
                               user_agent=request.headers.get("user-agent"))
        user.last_login_at = clock.now()
        out = _user_out(user)
    set_session_cookie(response, issued)
    return out


@router.post("/logout", status_code=204)
def logout(response: Response, viewer: Viewer | None = Depends(optional_viewer)) -> Response:
    """Revoke the session and clear the cookie. A stale cookie (expired, revoked, or from a reset database)
    is cleared too, so the browser never keeps a cookie the API rejects."""
    if viewer is not None:
        with write_tx() as s:
            session = s.get(UserSession, viewer.session_id)
            if session is not None and session.revoked_at is None:
                session.revoked_at = clock.now()
    response.status_code = 204
    clear_session_cookie(response)
    return response
