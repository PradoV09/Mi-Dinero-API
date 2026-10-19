from datetime import datetime, timezone

from app.models import Category, User
from tests.integration.helpers import CATEGORIES_URL, login

SYSTEM_INCOME = {"Salario", "Freelance", "Inversiones", "Otros ingresos"}


async def test_categories_require_authentication(client) -> None:
    assert (await client.get(CATEGORIES_URL)).status_code == 401


async def test_lists_system_categories_filtered_by_type(
    client, email_provider
) -> None:
    await login(client, email_provider)

    response = await client.get(
        CATEGORIES_URL, params={"type": "income", "page_size": 100}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    assert {category["name"] for category in body["items"]} == SYSTEM_INCOME
    assert all(category["is_system"] for category in body["items"])


async def test_create_custom_category_is_visible_only_to_owner(
    client, db_session, email_provider
) -> None:
    headers = await login(client, email_provider)

    created = await client.post(
        CATEGORIES_URL,
        json={"type": "expense", "name": "  Mascotas  "},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json() == {
        "id": created.json()["id"],
        "name": "Mascotas",
        "type": "expense",
        "is_system": False,
    }

    duplicate = await client.post(
        CATEGORIES_URL,
        json={"type": "expense", "name": "mascotas"},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "category_name_taken"

    same_name_other_type = await client.post(
        CATEGORIES_URL,
        json={"type": "income", "name": "Mascotas"},
        headers=headers,
    )
    assert same_name_other_type.status_code == 201

    foreign = User(
        email="otro@example.com",
        name="Otro",
        password_hash="x",
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(foreign)
    await db_session.flush()
    db_session.add(
        Category(user_id=foreign.id, type="expense", name="Viajes")
    )
    await db_session.commit()

    listing = await client.get(
        CATEGORIES_URL, params={"type": "expense", "page_size": 100}
    )
    names = {category["name"] for category in listing.json()["items"]}
    assert "Mascotas" in names
    assert "Viajes" not in names


async def test_create_category_validates_payload(
    client, email_provider
) -> None:
    headers = await login(client, email_provider)

    invalid_type = await client.post(
        CATEGORIES_URL,
        json={"type": "transfer", "name": "Otra"},
        headers=headers,
    )
    assert invalid_type.status_code == 422

    empty_name = await client.post(
        CATEGORIES_URL,
        json={"type": "expense", "name": "   "},
        headers=headers,
    )
    assert empty_name.status_code == 422

    mass_assignment = await client.post(
        CATEGORIES_URL,
        json={"type": "expense", "name": "Otra", "user_id": None},
        headers=headers,
    )
    assert mass_assignment.status_code == 422


async def test_create_category_requires_csrf(client, email_provider) -> None:
    await login(client, email_provider)

    response = await client.post(
        CATEGORIES_URL, json={"type": "expense", "name": "Sin CSRF"}
    )

    assert response.status_code == 403
