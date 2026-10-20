"""Sunucu tarafı oturumlar (ADR-1).

Çerezde 256 bitlik rastgele belirteç durur; veritabanında yalnızca SHA-256 özeti tutulur
(veritabanı sızarsa oturumlar ele geçirilemez). Oturum sabit süre sonunda biter; çıkışta silinir.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AuthSession, User


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> str:
    """Yeni oturum açar ve çereze yazılacak belirteci döndürür. Kullanıcının süresi dolmuş
    oturumları da temizlenir."""
    now = datetime.now(UTC)
    db.execute(
        delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.expires_at <= now)
    )
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=_digest(token),
            user_id=user.id,
            expires_at=now + timedelta(hours=settings.session_ttl_hours),
        )
    )
    db.commit()
    return token


def user_for_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    return db.scalar(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == _digest(token),
            AuthSession.expires_at > datetime.now(UTC),
        )
    )


def end_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == _digest(token)))
        db.commit()


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
