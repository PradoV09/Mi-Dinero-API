import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.core.crypto import decrypt_field
from app.models import Account, Category, IdempotencyKey, Transaction, User
from app.services.cleanup import purge_expired_idempotency_keys
from app.services.idempotency import build_request_hash
from tests.integration.helpers import (
    ACCOUNTS_URL,
    TRANSACTIONS_URL,
    create_account,
    create_transaction,
    login,
    system_category,
)


async def _rows(session, model):
    result = await session.execute(select(model))
    return result.scalars().all()


async def _foreign_account(session, name: str = "Ajena") -> Account:
    foreign = User(
        email="otro@example.com",
        name="Otro",
        password_hash="x",
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(foreign)
    await session.flush()
    account = Account(
        user_id=foreign.id,
        name="cifrado",
        name_fingerprint=uuid.uuid4().hex + uuid.uuid4().hex,
        account_type_code="cash",
        currency_code="COP",
        opening_balance=Decimal("0.00"),
    )
    session.add(account)
    await session.commit()
    return account


async def test_transactions_require_authentication(client) -> None:
    assert (await client.get(TRANSACTIONS_URL)).status_code == 401
    assert (
        await client.post(
            TRANSACTIONS_URL,
            json={},
            headers={"Idempotency-Key": "x"},
        )
    ).status_code == 401
    assert (
        await client.patch(
            f"{TRANSACTIONS_URL}/{uuid.uuid4()}",
            json={},
            headers={"Idempotency-Key": "x"},
        )
    ).status_code == 401
    assert (
        await client.delete(f"{TRANSACTIONS_URL}/{uuid.uuid4()}")
    ).status_code == 401


async def test_create_income_updates_balance_and_encrypts_description(
    client, db_session, email_provider
) -> None:
    headers = await login(client, email_provider)
    account = (
        await create_account(client, headers, opening_balance="1000.00")
    ).json()
    salary = await system_category(client, "income", "Salario")

    response = await create_transaction(
        client,
        headers,
        account_id=account["id"],
        category_id=salary["id"],
        amount="500.00",
        transaction_type="income",
        transaction_date="2026-10-01",
        description="  Pago mensual  ",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "income"
    assert body["amount"] == "500.00"
    assert body["currency_code"] == "COP"
    assert body["category_name"] == "Salario"
    assert body["description"] == "Pago mensual"
    assert "user_id" not in body

    stored = (await _rows(db_session, Transaction))[0]
    assert stored.description is not None
    assert stored.description != "Pago mensual"
    assert decrypt_field(stored.description) == "Pago mensual"

    account_after = await client.get(f"{ACCOUNTS_URL}/{account['id']}")
    assert account_after.json()["balance"] == "1500.00"
    assert account_after.json()["opening_balance"] == "1000.00"

    listing = await client.get(ACCOUNTS_URL)
    assert listing.json()["balances"] == [
        {"currency_code": "COP", "balance": "1500.00"}
    ]


async def test_create_expense_subtracts_from_balance(
    client, email_provider
) -> None:
    headers = await login(client, email_provider)
    account = (await create_account(client, headers, opening_balance="100.00")).json()
    food = await system_category(client, "expense", "Alimentacion")

    response = await create_transaction(
        client,
        headers,
        account_id=account["id"],
        category_id=food["id"],
        amount="30.50",
        transaction_type="expense",
    )

    assert response.status_code == 201
    account_after = await client.get(f"{ACCOUNTS_URL}/{account['id']}")
    assert account_after.json()["balance"] == "69.50"


async def test_create_transaction_validates_business_rules(
    client, db_session, email_provider
) -> None:
    headers = await login(client, email_provider)
    account = (await create_account(client, headers, opening_balance="100.00")).json()
    salary = await system_category(client, "income", "Salario")
    food = await system_category(client, "expense", "Alimentacion")

    zero = await create_transaction(
        client, headers, account["id"], food["id"], amount="0.00"
    )
    assert zero.status_code == 422

    negative = await create_transaction(
        client, headers, account["id"], food["id"], amount="-5.00"
    )
    assert negative.status_code == 422

    bad_scale = await create_transaction(
        client, headers, account["id"], food["id"], amount="10.555"
    )
    assert bad_scale.status_code == 422
    assert bad_scale.json()["error"]["code"] == "invalid_amount_scale"

    mismatch = await create_transaction(
        client, headers, account["id"], salary["id"], transaction_type="expense"
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "category_type_mismatch"

    archived = (
        await create_account(client, headers, name="Vieja")
    ).json()
    assert (
        await client.post(
            f"{ACCOUNTS_URL}/{archived['id']}/archive", headers=headers
        )
    ).status_code == 200
    archived_use = await create_transaction(
        client, headers, archived["id"], food["id"]
    )
    assert archived_use.status_code == 409
    assert archived_use.json()["error"]["code"] == "account_archived"

    foreign_account = await _foreign_account(db_session)
    foreign_account_use = await create_transaction(
        client, headers, str(foreign_account.id), food["id"]
    )
    assert foreign_account_use.status_code == 404
    assert foreign_account_use.json()["error"]["code"] == "account_not_found"

    missing_key = await client.post(
        TRANSACTIONS_URL,
        json={
            "type": "expense",
            "account_id": account["id"],
            "category_id": food["id"],
            "amount": "10.00",
            "transaction_date": "2026-10-19",
        },
        headers=headers,
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["error"]["code"] == "idempotency_key_required"

    mass_assignment = await client.post(
        TRANSACTIONS_URL,
        json={
            "type": "expense",
            "account_id": account["id"],
            "category_id": food["id"],
            "amount": "10.00",
            "transaction_date": "2026-10-19",
            "user_id": account["id"],
        },
        headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert mass_assignment.status_code == 422


async def test_idempotency_key_replays_and_conflicts(
    client, db_session, email_provider
) -> None:
    headers = await login(client, email_provider)
    account = (await create_account(client, headers)).json()
    food = await system_category(client, "expense", "Alimentacion")
    key = uuid.uuid4().hex

    first = await create_transaction(
        client, headers, account["id"], food["id"], amount="10.00", key=key
    )
    replay = await create_transaction(
        client, headers, account["id"], food["id"], amount="10.00", key=key
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]
    assert len(await _rows(db_session, Transaction)) == 1

    conflict = await create_transaction(
        client, headers, account["id"], food["id"], amount="99.00", key=key
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_reused"

    new_key = await create_transaction(
        client, headers, account["id"], food["id"], amount="10.00"
    )
    assert new_key.status_code == 201
    assert new_key.json()["id"] != first.json()["id"]
    assert len(await _rows(db_session, Transaction)) == 2


async def test_idempotency_in_progress_expired_and_long_key(
    client, db_session, email_provider
) -> None:
    headers = await login(client, email_provider)
    account = (await create_account(client, headers)).json()
    food = await system_category(client, "expense", "Alimentacion")
    user = (await _rows(db_session, User))[0]
    key = uuid.uuid4().hex
    body = {
        "type": "expense",
        "account_id": account["id"],
        "category_id": food["id"],
        "amount": "10.00",
        "transaction_date": "2026-10-19",
        "description": None,
    }
    record = IdempotencyKey(
        user_id=user.id,
        key=key,
        method="POST",
        path="/api/v1/transactions",
        request_hash=build_request_hash(
            user.id, "POST", "/api/v1/transactions", body
        ),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(record)
    await db_session.commit()

    in_progress = await client.post(
        TRANSACTIONS_URL,
        json=body,
        headers={**headers, "Idempotency-Key": key},
    )
    assert in_progress.status_code == 409
    assert in_progress.json()["error"]["code"] == "idempotency_key_in_progress"

    record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    reused_after_expiry = await client.post(
        TRANSACTIONS_URL,
        json=body,
        headers={**headers, "Idempotency-Key": key},
    )
    assert reused_after_expiry.status_code == 201

    too_long = await client.post(
        TRANSACTIONS_URL,
        json=body,
        headers={**headers, "Idempotency-Key": "x" * 129},
    )
    assert too_long.status_code == 400
    assert too_long.json()["error"]["code"] == "invalid_idempotency_key"


async def test_update_transaction_recalculates_and_is_idempotent(
    client, db_session, email_provider
) -> None:
    headers = await login(client, email_provider)
    account = (await create_account(client, headers, opening_balance="100.00")).json()
    food = await system_category(client, "expense", "Alimentacion")
    salary = await system_category(client, "income", "Salario")
    created = (
        await create_transaction(
            client, headers, account["id"], food["id"], amount="10.00"
        )
    ).json()
    key = uuid.uuid4().hex
    payload = {"amount": "25.50", "description": "  Actualizada  "}

    updated = await client.patch(
        f"{TRANSACTIONS_URL}/{created['id']}",
        json=payload,
        headers={**headers, "Idempotency-Key": key},
    )
    replay = await client.patch(
        f"{TRANSACTIONS_URL}/{created['id']}",
        json=payload,
        headers={**headers, "Idempotency-Key": key},
    )

    assert updated.status_code == 200
    assert updated.json()["amount"] == "25.50"
    assert updated.json()["description"] == "Actualizada"
    assert replay.status_code == 200
    assert replay.json() == updated.json()

    account_after = await client.get(f"{ACCOUNTS_URL}/{account['id']}")
    assert account_after.json()["balance"] == "74.50"

    cleared = await client.patch(
        f"{TRANSACTIONS_URL}/{created['id']}",
        json={"description": None},
        headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert cleared.status_code == 200
    assert cleared.json()["description"] is None

    mismatch = await client.patch(
        f"{TRANSACTIONS_URL}/{created['id']}",
        json={"category_id": salary["id"]},
        headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "category_type_mismatch"

    empty = await client.patch(
        f"{TRANSACTIONS_URL}/{created['id']}",
        json={},
        headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert empty.status_code == 422

    null_type = await client.patch(
        f"{TRANSACTIONS_URL}/{created['id']}",
        json={"type": None},
        headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert null_type.status_code == 422


async def test_update_and_delete_do_not_cross_users(
    client, db_session, email_provider
) -> None:
    headers = await login(client, email_provider)
    account = (await create_account(client, headers)).json()
    food = await system_category(client, "expense", "Alimentacion")
    await create_transaction(
        client, headers, account["id"], food["id"], amount="5.00"
    )

    foreign = await _foreign_account(db_session)
    foreign_category = await db_session.scalar(
        select(Category).where(Category.user_id.is_(None), Category.type == "expense")
    )
    foreign_transaction = Transaction(
        user_id=foreign.user_id,
        account_id=foreign.id,
        category_id=foreign_category.id,
        type="expense",
        amount=Decimal("3.00"),
        transaction_date=datetime.now(timezone.utc).date(),
    )
    db_session.add(foreign_transaction)
    await db_session.commit()

    assert (
        await client.patch(
            f"{TRANSACTIONS_URL}/{foreign_transaction.id}",
            json={"amount": "4.00"},
            headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
        )
    ).status_code == 404
    assert (
        await client.delete(
            f"{TRANSACTIONS_URL}/{foreign_transaction.id}", headers=headers
        )
    ).status_code == 404

    listing = await client.get(TRANSACTIONS_URL)
    assert listing.json()["total"] == 1


async def test_delete_transaction_restores_balance(
    client, email_provider
) -> None:
    headers = await login(client, email_provider)
    account = (await create_account(client, headers, opening_balance="100.00")).json()
    food = await system_category(client, "expense", "Alimentacion")
    created = (
        await create_transaction(
            client, headers, account["id"], food["id"], amount="40.00"
        )
    ).json()

    deleted = await client.delete(
        f"{TRANSACTIONS_URL}/{created['id']}", headers=headers
    )
    assert deleted.status_code == 204
    assert deleted.text == ""

    assert (
        await client.delete(
            f"{TRANSACTIONS_URL}/{created['id']}", headers=headers
        )
    ).status_code == 404

    account_after = await client.get(f"{ACCOUNTS_URL}/{account['id']}")
    assert account_after.json()["balance"] == "100.00"
    assert (await client.get(TRANSACTIONS_URL)).json()["total"] == 0


async def test_list_filters_and_pagination(client, email_provider) -> None:
    headers = await login(client, email_provider)
    first = (await create_account(client, headers, name="Uno")).json()
    second = (
        await create_account(
            client,
            headers,
            name="Dos",
            account_type="bank",
            currency_code="USD",
        )
    ).json()
    salary = await system_category(client, "income", "Salario")
    food = await system_category(client, "expense", "Alimentacion")
    transport = await system_category(client, "expense", "Transporte")

    await create_transaction(
        client, headers, first["id"], salary["id"], amount="100.00",
        transaction_type="income", transaction_date="2026-10-01",
    )
    await create_transaction(
        client, headers, first["id"], food["id"], amount="20.00",
        transaction_type="expense", transaction_date="2026-10-15",
    )
    await create_transaction(
        client, headers, first["id"], transport["id"], amount="30.00",
        transaction_type="expense", transaction_date="2026-10-31",
    )
    await create_transaction(
        client, headers, second["id"], salary["id"], amount="50.00",
        transaction_type="income", transaction_date="2026-10-20",
    )

    ranged = await client.get(
        TRANSACTIONS_URL,
        params={"from": "2026-10-15", "to": "2026-10-31"},
    )
    assert ranged.json()["total"] == 3

    expenses = await client.get(
        TRANSACTIONS_URL, params={"type": "expense"}
    )
    assert expenses.json()["total"] == 2

    by_account = await client.get(
        TRANSACTIONS_URL, params={"account_id": second["id"]}
    )
    assert by_account.json()["total"] == 1
    assert by_account.json()["items"][0]["currency_code"] == "USD"

    by_category = await client.get(
        TRANSACTIONS_URL, params={"category_id": food["id"]}
    )
    assert by_category.json()["total"] == 1

    second_page = await client.get(
        TRANSACTIONS_URL, params={"page": 2, "page_size": 2}
    )
    assert second_page.json()["total"] == 4
    assert len(second_page.json()["items"]) == 2

    first_page = await client.get(TRANSACTIONS_URL, params={"page_size": 100})
    dates = [item["transaction_date"] for item in first_page.json()["items"]]
    assert dates == ["2026-10-31", "2026-10-20", "2026-10-15", "2026-10-01"]

    invalid_range = await client.get(
        TRANSACTIONS_URL,
        params={"from": "2026-10-31", "to": "2026-10-01"},
    )
    assert invalid_range.status_code == 422
    assert invalid_range.json()["error"]["code"] == "invalid_date_range"


async def test_currency_change_is_blocked_with_transactions(
    client, email_provider
) -> None:
    headers = await login(client, email_provider)
    account = (await create_account(client, headers)).json()
    food = await system_category(client, "expense", "Alimentacion")
    await create_transaction(
        client, headers, account["id"], food["id"], amount="10.00"
    )

    response = await client.patch(
        f"{ACCOUNTS_URL}/{account['id']}",
        json={"currency_code": "USD"},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "currency_change_not_allowed"


async def test_purge_expired_idempotency_keys(
    client, db_session, email_provider
) -> None:
    await login(client, email_provider)
    db_session.add(
        IdempotencyKey(
            user_id=(await _rows(db_session, User))[0].id,
            key="vieja",
            method="POST",
            path="/api/v1/transactions",
            request_hash="x",
            expires_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    assert await purge_expired_idempotency_keys(db_session) == 1
    assert await _rows(db_session, IdempotencyKey) == []
