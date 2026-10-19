import uuid
from decimal import Decimal

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Currency, Transaction


def _signed_amount():
    return case(
        (Transaction.type == "income", Transaction.amount),
        else_=-Transaction.amount,
    )


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


async def account_balances(
    session: AsyncSession,
    user_id: uuid.UUID,
    account_ids: set[uuid.UUID] | None = None,
) -> dict[uuid.UUID, Decimal]:
    statement = (
        select(
            Account.id,
            Account.opening_balance
            + func.coalesce(func.sum(_signed_amount()), 0),
        )
        .outerjoin(Transaction, Transaction.account_id == Account.id)
        .where(Account.user_id == user_id)
        .group_by(Account.id, Account.opening_balance)
    )
    if account_ids is not None:
        if not account_ids:
            return {}
        statement = statement.where(Account.id.in_(account_ids))
    rows = await session.execute(statement)
    return {account_id: balance for account_id, balance in rows.all()}


async def currency_balances(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[str, int, Decimal]]:
    rows = (
        await session.execute(
            select(Account.id, Account.currency_code, Currency.minor_units)
            .join(Currency, Currency.code == Account.currency_code)
            .where(Account.user_id == user_id)
            .where(Account.is_archived.is_(False))
        )
    ).all()
    if not rows:
        return []

    balances = await account_balances(
        session, user_id, {account_id for account_id, _, _ in rows}
    )
    totals: dict[str, tuple[int, Decimal]] = {}
    for account_id, currency_code, minor_units in rows:
        current_minor_units, current = totals.get(
            currency_code, (minor_units, Decimal("0"))
        )
        totals[currency_code] = (
            current_minor_units,
            current + balances[account_id],
        )
    return [
        (code, minor_units, total)
        for code, (minor_units, total) in sorted(totals.items())
    ]
