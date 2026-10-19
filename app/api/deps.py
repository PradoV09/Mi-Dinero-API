from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ApiError
from app.core.security import constant_time_equals, hash_token
from app.db.session import SessionLocal
from app.models import Session, User
from app.services.email import EmailProvider, build_email_provider


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def get_email_provider() -> EmailProvider:
    return build_email_provider()


async def get_current_user(
    request: Request, session: AsyncSession = Depends(get_db)
) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise ApiError(401, "not_authenticated", "No autenticado")

    result = await session.execute(
        select(Session)
        .where(Session.token_hash == hash_token(token))
        .where(Session.revoked_at.is_(None))
        .where(Session.expires_at > datetime.now(timezone.utc))
    )
    db_session = result.scalar_one_or_none()
    if db_session is None:
        raise ApiError(401, "not_authenticated", "Sesion invalida o expirada")

    user = await session.get(User, db_session.user_id)
    if user is None or user.email_verified_at is None:
        raise ApiError(401, "not_authenticated", "Sesion invalida o expirada")
    return user


async def require_csrf(request: Request) -> None:
    cookie = request.cookies.get(settings.csrf_cookie_name)
    header = request.headers.get(settings.csrf_header_name)
    if not cookie or not header or not constant_time_equals(cookie, header):
        raise ApiError(403, "csrf_failed", "Token CSRF invalido o ausente")
