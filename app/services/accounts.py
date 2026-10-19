import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def account_has_transactions(
    session: AsyncSession, account_id: uuid.UUID
) -> bool:
    table = await session.scalar(text("SELECT to_regclass('public.transactions')"))
    if table is None:
        return False
    exists = await session.scalar(
        text("SELECT EXISTS (SELECT 1 FROM transactions WHERE account_id = :id)"),
        {"id": account_id},
    )
    return bool(exists)
