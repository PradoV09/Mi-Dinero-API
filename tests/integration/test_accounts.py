import re
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.core.config import settings
from app.core.crypto import decrypt_field, encrypt_field, name_fingerprint
from app.models import Account, User

ACCOUNTS_URL = "/api/v1/accounts"
REGISTER_URL = "/api/v1/auth/register"
VERIFY_URL = "/api/v1/auth/verify-email"
LOGIN_URL = "/api/v1/auth/login"

DEFAULT_EMAIL = "ana@example.com"
DEFAULT_PASSWORD = "secreto123"


async def _login(client, provider, email: str = DEFAULT_EMAIL) -> dict[str, str]:
    await client.post(
        REGISTER_URL,
        json={"email": email, "name": "Ana", "password": DEFAULT_PASSWORD},
    )
    token = re.search(r"token=([A-Za-z0-9_\-]+)", provider.sent[-1].text).group(1)
    assert (await client.post(VERIFY_URL, json={"token": token})).status_code == 201
    assert (
        await client.post(
            LOGIN_URL, json={"email": email, "password": DEFAULT_PASSWORD}
        )
    ).status_code == 200
    csrf = client.cookies.get(settings.csrf_cookie_name)
    assert csrf
    return {settings.csrf_header_name: csrf}


async def _create(client, headers, **overrides):
    payload = {
        "name": "Efectivo",
        "account_type": "cash",
        "currency_code": "COP",
        "opening_balance": "1000.00",
    }
    payload.update(overrides)
    return await client.post(ACCOUNTS_URL, json=payload, headers=headers)


async def _rows(session, model):
    result = await session.execute(select(model))
    return result.scalars().all()


async def test_accounts_require_authentication(client) -> None:
    assert (await client.get(ACCOUNTS_URL)).status_code == 401
    assert (await client.post(ACCOUNTS_URL, json={})).status_code == 401
    assert (await client.get(f"{ACCOUNTS_URL}/00000000-0000-0000-0000-000000000000")).status_code == 401


async def test_create_account_encrypts_name_and_persists(
    client, db_session, email_provider
) -> None:
    headers = await _login(client, email_provider)

    response = await _create(client, headers, name="Cuenta principal")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Cuenta principal"
    assert body["opening_balance"] == "1000.00"
    assert "user_id" not in body

    stored = (await _rows(db_session, Account))[0]
    assert stored.name != "Cuenta principal"
    assert stored.name.startswith("v1:")
    assert decrypt_field(stored.name) == "Cuenta principal"
    assert stored.name_fingerprint == name_fingerprint("Cuenta principal")

    fetched = await client.get(f"{ACCOUNTS_URL}/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Cuenta principal"


async def test_duplicate_active_name_is_rejected_case_insensitively(
    client, email_provider
) -> None:
    headers = await _login(client, email_provider)
    first = await _create(client, headers)
    assert first.status_code == 201

    duplicate = await _create(client, headers, name="  efectivo ")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "account_name_taken"

    assert (
        await client.post(
            f"{ACCOUNTS_URL}/{first.json()['id']}/archive", headers=headers
        )
    ).status_code == 200
    reused = await _create(client, headers, name="efectivo")
    assert reused.status_code == 201


async def test_create_account_validates_fields(
    client, email_provider
) -> None:
    headers = await _login(client, email_provider)

    invalid_type = await _create(client, headers, account_type="nope")
    assert invalid_type.status_code == 422
    assert invalid_type.json()["error"]["code"] == "invalid_account_type"

    invalid_currency = await _create(client, headers, currency_code="XXX")
    assert invalid_currency.status_code == 422
    assert invalid_currency.json()["error"]["code"] == "invalid_currency"

    invalid_scale = await _create(client, headers, opening_balance="10.555")
    assert invalid_scale.status_code == 422
    assert invalid_scale.json()["error"]["code"] == "invalid_amount_scale"

    negative = await _create(client, headers, opening_balance="-10.00")
    assert negative.status_code == 422
    assert negative.json()["error"]["code"] == "negative_opening_balance_not_allowed"

    credit = await _create(
        client,
        headers,
        name="Visa",
        account_type="credit_card",
        opening_balance="-250000.00",
    )
    assert credit.status_code == 201
    assert credit.json()["opening_balance"] == "-250000.00"

    mass_assignment = await _create(
        client, headers, name="Otra", user_id=str(credit.json()["id"])
    )
    assert mass_assignment.status_code == 422


async def test_list_accounts_paginates_and_summarizes_by_currency(
    client, email_provider
) -> None:
    headers = await _login(client, email_provider)
    await _create(client, headers, name="Efectivo", opening_balance="1000.00")
    await _create(
        client,
        headers,
        name="Dolares",
        currency_code="USD",
        account_type="bank",
        opening_balance="20.50",
    )
    await _create(client, headers, name="Ahorros", account_type="savings", opening_balance="500.00")

    first_page = await client.get(ACCOUNTS_URL, params={"page_size": 2})
    assert first_page.status_code == 200
    body = first_page.json()
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["balances"] == [
        {"currency_code": "COP", "balance": "1500.00"},
        {"currency_code": "USD", "balance": "20.50"},
    ]

    second_page = await client.get(
        ACCOUNTS_URL, params={"page": 2, "page_size": 2}
    )
    assert len(second_page.json()["items"]) == 1


async def test_accounts_are_isolated_between_users(
    client, db_session, email_provider
) -> None:
    headers = await _login(client, email_provider)

    foreign = User(
        email="otro@example.com",
        name="Otro",
        password_hash="x",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(foreign)
    await db_session.flush()
    foreign_account = Account(
        user_id=foreign.id,
        name=encrypt_field("Ajena"),
        name_fingerprint=name_fingerprint("Ajena"),
        account_type_code="cash",
        currency_code="COP",
        opening_balance=Decimal("1.00"),
    )
    db_session.add(foreign_account)
    await db_session.commit()

    foreign_id = str(foreign_account.id)
    assert (await client.get(f"{ACCOUNTS_URL}/{foreign_id}")).status_code == 404
    assert (
        await client.patch(
            f"{ACCOUNTS_URL}/{foreign_id}", json={"name": "Robada"}, headers=headers
        )
    ).status_code == 404
    assert (
        await client.post(
            f"{ACCOUNTS_URL}/{foreign_id}/archive", headers=headers
        )
    ).status_code == 404

    listing = await client.get(ACCOUNTS_URL)
    assert listing.json()["total"] == 0
    assert listing.json()["items"] == []


async def test_update_account_and_currency_rules(
    client, db_session, email_provider, monkeypatch
) -> None:
    headers = await _login(client, email_provider)
    created = await _create(client, headers)
    account_id = created.json()["id"]

    renamed = await client.patch(
        f"{ACCOUNTS_URL}/{account_id}", json={"name": "Caja"}, headers=headers
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Caja"
    stored = (await _rows(db_session, Account))[0]
    assert decrypt_field(stored.name) == "Caja"

    changed = await client.patch(
        f"{ACCOUNTS_URL}/{account_id}",
        json={"currency_code": "USD", "account_type": "bank"},
        headers=headers,
    )
    assert changed.status_code == 200
    assert changed.json()["currency_code"] == "USD"
    assert changed.json()["account_type"] == "bank"

    from app.api.v1 import accounts as accounts_module

    async def fake_has_transactions(session, account_id):
        return True

    monkeypatch.setattr(
        accounts_module, "account_has_transactions", fake_has_transactions
    )
    blocked = await client.patch(
        f"{ACCOUNTS_URL}/{account_id}",
        json={"currency_code": "COP"},
        headers=headers,
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "currency_change_not_allowed"


async def test_update_rejects_mass_assignment_and_duplicates(
    client, email_provider
) -> None:
    headers = await _login(client, email_provider)
    first = await _create(client, headers)
    second = await _create(client, headers, name="Ahorros", account_type="savings")

    mass_assignment = await client.patch(
        f"{ACCOUNTS_URL}/{second.json()['id']}",
        json={"user_id": first.json()["id"]},
        headers=headers,
    )
    assert mass_assignment.status_code == 422

    duplicate = await client.patch(
        f"{ACCOUNTS_URL}/{second.json()['id']}",
        json={"name": "efectivo"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    empty = await client.patch(
        f"{ACCOUNTS_URL}/{second.json()['id']}", json={}, headers=headers
    )
    assert empty.status_code == 422

    null_field = await client.patch(
        f"{ACCOUNTS_URL}/{second.json()['id']}",
        json={"name": None},
        headers=headers,
    )
    assert null_field.status_code == 422


async def test_archive_is_idempotent_and_filters_listing(
    client, email_provider
) -> None:
    headers = await _login(client, email_provider)
    created = await _create(client, headers)
    account_id = created.json()["id"]

    first = await client.post(f"{ACCOUNTS_URL}/{account_id}/archive", headers=headers)
    assert first.status_code == 200
    assert first.json()["is_archived"] is True
    assert first.json()["archived_at"] is not None

    second = await client.post(f"{ACCOUNTS_URL}/{account_id}/archive", headers=headers)
    assert second.status_code == 200
    assert second.json()["is_archived"] is True

    default_list = await client.get(ACCOUNTS_URL)
    assert default_list.json()["total"] == 0
    assert default_list.json()["balances"] == []

    with_archived = await client.get(ACCOUNTS_URL, params={"include_archived": True})
    assert with_archived.json()["total"] == 1
    assert with_archived.json()["balances"] == []


async def test_mutations_require_csrf(client, email_provider) -> None:
    await _login(client, email_provider)

    response = await client.post(
        ACCOUNTS_URL,
        json={
            "name": "Sin CSRF",
            "account_type": "cash",
            "currency_code": "COP",
            "opening_balance": "0.00",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
