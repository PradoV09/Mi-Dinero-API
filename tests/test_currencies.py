from sqlalchemy import select

from app.models import Currency


async def test_currencies_are_seeded(db_session) -> None:
    result = await db_session.execute(select(Currency).order_by(Currency.code))
    currencies = result.scalars().all()

    assert [currency.code for currency in currencies] == ["COP", "EUR", "USD"]
    assert all(currency.is_active for currency in currencies)
    assert all(currency.minor_units == 2 for currency in currencies)


async def test_currency_has_timestamps(db_session) -> None:
    result = await db_session.execute(
        select(Currency).where(Currency.code == "COP")
    )
    currency = result.scalar_one()

    assert currency.created_at is not None
    assert currency.updated_at is not None
    assert currency.name == "Peso colombiano"
