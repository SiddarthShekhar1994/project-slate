"""Local accounts: scrypt password hashes and opaque session tokens.

The session cookie holds a random token. The database stores only its SHA-256,
so a database leak does not hand out live sessions.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import AuthSession, User

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
MIN_PASSWORD = 8


class AuthError(ValueError):
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p),
                            dklen=len(digest_hex) // 2)
    return hmac.compare_digest(digest.hex(), digest_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalise_email(email: str) -> str:
    return email.strip().lower()


def create_user(db: Session, email: str, password: str, display_name: str) -> User:
    email = normalise_email(email)
    if "@" not in email or len(email) > 320:
        raise AuthError("Enter a valid email address.")
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"Use at least {MIN_PASSWORD} characters for your password.")
    if db.scalar(select(User).where(User.email == email)):
        raise AuthError("An account with that email already exists.")
    user = User(email=email, display_name=display_name.strip()[:80] or email.split("@")[0],
                password_hash=hash_password(password))
    db.add(user)
    db.flush()
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalise_email(email)))
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("That email and password don't match an account.")
    return user


def start_session(db: Session, user: User, days: int) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=_token_hash(token),
                       expires_at=datetime.now(timezone.utc) + timedelta(days=days)))
    db.flush()
    return token


def user_for_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if session is None or session.expires_at <= datetime.now(timezone.utc):
        return None
    return session.user


def end_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
