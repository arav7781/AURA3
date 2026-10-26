"""Passwords, sessions and the session cookie.

The browser only talks to the Next.js origin; ``/api/*`` is rewritten to this service, so the session
cookie is first-party: HttpOnly, SameSite=Lax. It carries an HS256 JWT whose ``sid`` must match a live
row in ``sessions`` (so logout and revocation take effect immediately).
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Response
from sqlalchemy.orm import Session

from aura.core import clock
from aura.core.config import get_settings
from aura.models import User, UserSession

COOKIE_NAME = "aura_session"
CSRF_HEADER = "X-Aura-CSRF"
_hasher = PasswordHasher()  # argon2id defaults


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


@dataclass(frozen=True)
class IssuedSession:
    sid: str
    token: str
    expires_at: datetime


def issue_session(s: Session, user: User, *, ip: str | None = None, user_agent: str | None = None) -> IssuedSession:
    settings = get_settings()
    now = clock.now()
    expires = now + timedelta(days=settings.session_days)
    sid = secrets.token_urlsafe(32)
    s.add(UserSession(id=sid, user_id=user.id, expires_at=expires, ip=ip, user_agent=(user_agent or "")[:300]))
    claims = {
        "sub": user.id,
        "sid": sid,
        "role": user.role,
        "adm": bool(user.is_admin),
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    token = jwt.encode(claims, settings.require_session_secret(), algorithm="HS256")
    return IssuedSession(sid=sid, token=token, expires_at=expires)


def decode_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        # Expiry is checked against the application clock (which demo mode can fast-forward), not wall time.
        claims = jwt.decode(
            token,
            settings.require_session_secret(),
            algorithms=["HS256"],
            options={"verify_exp": False, "verify_iat": False, "verify_nbf": False, "require": ["sub", "sid", "exp"]},
        )
    except jwt.PyJWTError:
        return None
    if int(claims.get("exp", 0)) < int(clock.now().timestamp()):
        return None
    return claims


def set_session_cookie(response: Response, issued: IssuedSession) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        issued.token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", samesite="lax", httponly=True)
