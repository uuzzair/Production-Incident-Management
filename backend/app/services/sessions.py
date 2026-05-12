import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from secrets import compare_digest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.models.user import User, UserSession


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str, settings: Settings) -> str:
    return hmac.new(
        settings.session_cookie_secret.encode("utf-8"),
        f"session:{token}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def hash_csrf_token(token: str, settings: Settings) -> str:
    return hmac.new(
        settings.session_cookie_secret.encode("utf-8"),
        f"csrf:{token}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def create_session(session: AsyncSession, user: User, settings: Settings) -> tuple[str, UserSession]:
    token = generate_session_token()
    now = utc_now()
    user_session = UserSession(
        session_token_hash=hash_session_token(token, settings),
        user_id=user.id,
        expires_at=now + timedelta(hours=settings.session_expiry_hours),
        created_at=now,
        last_seen_at=now,
    )
    user.last_login_at = now
    session.add(user_session)
    await session.commit()
    await session.refresh(user_session)
    return token, user_session


async def get_valid_session(
    session: AsyncSession,
    token: str,
    settings: Settings,
    *,
    update_last_seen: bool = True,
) -> UserSession | None:
    token_hash = hash_session_token(token, settings)
    result = await session.execute(
        select(UserSession)
        .options(selectinload(UserSession.user))
        .where(UserSession.session_token_hash == token_hash)
    )
    user_session = result.scalar_one_or_none()
    now = utc_now()
    if user_session is None:
        return None
    if user_session.revoked_at is not None:
        return None
    if as_utc(user_session.expires_at) <= now:
        return None
    if not user_session.user.is_active:
        return None

    if update_last_seen:
        user_session.last_seen_at = now
        await session.commit()
    return user_session


async def rotate_csrf_token(session: AsyncSession, user_session: UserSession, settings: Settings) -> str:
    token = generate_csrf_token()
    user_session.csrf_token_hash = hash_csrf_token(token, settings)
    await session.commit()
    return token


def is_valid_csrf_token(user_session: UserSession, token: str, settings: Settings) -> bool:
    if not user_session.csrf_token_hash:
        return False
    return compare_digest(user_session.csrf_token_hash, hash_csrf_token(token, settings))


async def revoke_session(session: AsyncSession, user_session: UserSession) -> None:
    if user_session.revoked_at is None:
        user_session.revoked_at = utc_now()
        user_session.csrf_token_hash = None
        await session.commit()
