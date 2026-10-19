import re
import uuid

from app.core.config import settings

REGISTER_URL = "/api/v1/auth/register"
VERIFY_URL = "/api/v1/auth/verify-email"
LOGIN_URL = "/api/v1/auth/login"
ACCOUNTS_URL = "/api/v1/accounts"
CATEGORIES_URL = "/api/v1/categories"
TRANSACTIONS_URL = "/api/v1/transactions"

DEFAULT_EMAIL = "ana@example.com"
DEFAULT_PASSWORD = "secreto123"


async def login(
    client, provider, email: str = DEFAULT_EMAIL, password: str = DEFAULT_PASSWORD
) -> dict[str, str]:
    await client.post(
        REGISTER_URL,
        json={"email": email, "name": "Ana", "password": password},
    )
    token = re.search(r"token=([A-Za-z0-9_\-]+)", provider.sent[-1].text).group(1)
    assert (await client.post(VERIFY_URL, json={"token": token})).status_code == 201
    assert (
        await client.post(LOGIN_URL, json={"email": email, "password": password})
    ).status_code == 200
    csrf = client.cookies.get(settings.csrf_cookie_name)
    assert csrf
    return {settings.csrf_header_name: csrf}


async def create_account(
    client,
    headers,
    name: str = "Efectivo",
    account_type: str = "cash",
    currency_code: str = "COP",
    opening_balance: str = "0.00",
):
    return await client.post(
        ACCOUNTS_URL,
        json={
            "name": name,
            "account_type": account_type,
            "currency_code": currency_code,
            "opening_balance": opening_balance,
        },
        headers=headers,
    )


async def system_category(client, category_type: str, name: str) -> dict:
    response = await client.get(
        CATEGORIES_URL, params={"type": category_type, "page_size": 100}
    )
    assert response.status_code == 200
    return next(
        category
        for category in response.json()["items"]
        if category["name"] == name
    )


async def create_transaction(
    client,
    headers,
    account_id: str,
    category_id: str,
    amount: str = "10.00",
    transaction_type: str = "expense",
    transaction_date: str = "2026-10-19",
    description: str | None = None,
    key: str | None = None,
):
    request_headers = {**headers, "Idempotency-Key": key or uuid.uuid4().hex}
    body = {
        "type": transaction_type,
        "account_id": account_id,
        "category_id": category_id,
        "amount": amount,
        "transaction_date": transaction_date,
    }
    if description is not None:
        body["description"] = description
    return await client.post(
        TRANSACTIONS_URL, json=body, headers=request_headers
    )
