import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select

from .models import AccessSession, User


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310_000).hex()
    return f"pbkdf2_sha256$310000${salt}${digest}"


def verify_password(password: str, value: str) -> bool:
    _, rounds, salt, expected = value.split("$")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
    return hmac.compare_digest(actual, expected)


def token_digest(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_session(db, user: User):
    token = secrets.token_urlsafe(36)
    db.add(
        AccessSession(
            token_hash=token_digest(token),
            user_id=user.id,
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
        )
    )
    db.commit()
    return token


def authenticate(db, token: str):
    session = db.get(AccessSession, token_digest(token))
    if not session or session.expires_at <= datetime.now(timezone.utc).isoformat():
        raise HTTPException(401, "登录已过期，请重新登录")
    user = db.scalar(select(User).where(User.id == session.user_id, User.active.is_(True)))
    if not user:
        raise HTTPException(401, "账号不可用")
    return user


def public_user(user: User):
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}
