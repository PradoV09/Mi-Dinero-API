from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IdempotencyKey, PendingRegistration


async def purge_expired_pending_registrations(session: AsyncSession) -> int:
    result = await session.execute(
        delete(PendingRegistration).where(
            PendingRegistration.expires_at < datetime.now(timezone.utc)
        )
    )
    await session.commit()
    return result.rowcount or 0


async def purge_expired_idempotency_keys(session: AsyncSession) -> int:
    result = await session.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.expires_at < datetime.now(timezone.utc)
        )
    )
    await session.commit()
    return result.rowcount or 0
