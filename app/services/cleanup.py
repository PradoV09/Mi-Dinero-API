from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PendingRegistration


async def purge_expired_pending_registrations(session: AsyncSession) -> int:
    result = await session.execute(
        delete(PendingRegistration).where(
            PendingRegistration.expires_at < datetime.now(timezone.utc)
        )
    )
    await session.commit()
    return result.rowcount or 0
