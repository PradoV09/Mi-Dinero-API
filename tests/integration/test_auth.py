import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import OutboxEmail, PendingRegistration, Session, User
from app.services.cleanup import purge_expired_pending_registrations
from app.services.email import flush_outbox

TOKEN_RE = re.compile(r"token=([A-Za-z0-9_\-]+)")
REGISTER_URL = "/api/v1/auth/register"
VERIFY_URL = "/api/v1/auth/verify-email"
LOGIN_URL = "/api/v1/auth/login"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"
FORGOT_URL = "/api/v1/auth/forgot-password"
RESET_URL = "/api/v1/auth/reset-password"

DEFAULT_EMAIL = "ana@example.com"
DEFAULT_PASSWORD = "secreto123"


def token_from(provider, index: int = -1) -> str:
    match = TOKEN_RE.search(provider.sent[index].text)
    assert match is not None
    return match.group(1)


async def register(
    client, email: str = DEFAULT_EMAIL, password: str = DEFAULT_PASSWORD
):
    return await client.post(
        REGISTER_URL,
        json={"email": email, "name": "Ana", "password": password},
    )


async def confirm(client, provider, index: int = 0):
    return await client.post(VERIFY_URL, json={"token": token_from(provider, index)})


async def login(client, email: str = DEFAULT_EMAIL, password: str = DEFAULT_PASSWORD):
    return await client.post(LOGIN_URL, json={"email": email, "password": password})


async def _rows(session, model):
    result = await session.execute(select(model))
    return result.scalars().all()


async def test_register_creates_pending_and_not_user(
    client, db_session, email_provider
) -> None:
    response = await register(client)

    assert response.status_code == 202
    assert response.json() == {
        "message": "Si el correo es valido, recibiras un mensaje para continuar."
    }
    pending = await _rows(db_session, PendingRegistration)
    assert len(pending) == 1
    assert pending[0].email == DEFAULT_EMAIL
    assert pending[0].password_hash.startswith("$argon2id$")
    assert await _rows(db_session, User) == []
    assert email_provider.sent[0].subject == "Confirma tu correo en Mi Dinero"


async def test_verify_email_creates_user_and_sends_welcome(
    client, db_session, email_provider
) -> None:
    await register(client)
    response = await confirm(client, email_provider)

    assert response.status_code == 201
    users = await _rows(db_session, User)
    assert len(users) == 1
    assert users[0].email == DEFAULT_EMAIL
    assert users[0].email_verified_at is not None
    assert await _rows(db_session, PendingRegistration) == []
    assert [email.subject for email in email_provider.sent][-1] == (
        "¡Bienvenido a Mi Dinero!"
    )


async def test_expired_token_fails(client, db_session, email_provider) -> None:
    await register(client)
    pending = (await _rows(db_session, PendingRegistration))[0]
    pending.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()

    response = await confirm(client, email_provider)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "expired_token"


async def test_reused_token_fails(client, db_session, email_provider) -> None:
    await register(client)
    assert (await confirm(client, email_provider)).status_code == 201

    response = await confirm(client, email_provider, index=0)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_token"


async def test_false_token_fails(client) -> None:
    response = await client.post(VERIFY_URL, json={"token": "no-existe"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_token"


async def test_login_before_and_after_confirmation(
    client, email_provider
) -> None:
    await register(client)
    before = await login(client)
    assert before.status_code == 401
    assert before.json()["error"]["code"] == "invalid_credentials"

    await confirm(client, email_provider)
    after = await login(client)
    assert after.status_code == 200
    assert after.json()["email"] == DEFAULT_EMAIL


async def test_register_is_anti_enumeration(
    client, db_session, email_provider
) -> None:
    new = await register(client, email="nuevo@example.com")
    existing_pending = await register(client, email="nuevo@example.com")

    assert (await confirm(client, email_provider, index=-1)).status_code == 201
    existing_user = await register(client, email="nuevo@example.com")

    assert new.status_code == existing_pending.status_code == existing_user.status_code
    assert new.json() == existing_pending.json() == existing_user.json()
    assert email_provider.sent[-1].subject == "Ya tienes una cuenta en Mi Dinero"


async def test_logout_invalidates_session(client, email_provider) -> None:
    await register(client)
    await confirm(client, email_provider)
    assert (await login(client)).status_code == 200
    assert (await client.get(ME_URL)).status_code == 200

    csrf = client.cookies.get("mi_dinero_csrf")
    response = await client.post(LOGOUT_URL, headers={"X-CSRF-Token": csrf})

    assert response.status_code == 200
    assert (await client.get(ME_URL)).status_code == 401


async def test_private_route_without_session_is_401(client) -> None:
    response = await client.get(ME_URL)

    assert response.status_code == 401


async def test_logout_without_csrf_is_forbidden(client, email_provider) -> None:
    await register(client)
    await confirm(client, email_provider)
    await login(client)

    response = await client.post(LOGOUT_URL)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


async def test_register_rate_limit(client) -> None:
    for index in range(5):
        response = await register(client, email=f"user{index}@example.com")
        assert response.status_code == 202

    response = await register(client, email="user99@example.com")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


async def test_full_password_reset_flow(
    client, db_session, email_provider
) -> None:
    await register(client)
    await confirm(client, email_provider)
    await login(client)

    forgot = await client.post(FORGOT_URL, json={"email": DEFAULT_EMAIL})
    assert forgot.status_code == 202

    reset = await client.post(
        RESET_URL,
        json={"token": token_from(email_provider), "new_password": "nuevaclave1"},
    )
    assert reset.status_code == 200

    assert (await client.get(ME_URL)).status_code == 401
    assert (await login(client, password=DEFAULT_PASSWORD)).status_code == 401
    assert (await login(client, password="nuevaclave1")).status_code == 200
    active = await db_session.execute(
        select(Session).where(Session.revoked_at.is_(None))
    )
    assert len(active.scalars().all()) == 1


async def test_reset_token_is_single_use(client, email_provider) -> None:
    await register(client)
    await confirm(client, email_provider)
    await client.post(FORGOT_URL, json={"email": DEFAULT_EMAIL})
    token = token_from(email_provider)

    first = await client.post(
        RESET_URL, json={"token": token, "new_password": "nuevaclave1"}
    )
    second = await client.post(
        RESET_URL, json={"token": token, "new_password": "nuevaclave2"}
    )

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_token"


async def test_email_provider_failure_does_not_break_register(
    client, db_session, email_provider
) -> None:
    email_provider.fail_next = 1

    response = await register(client)

    assert response.status_code == 202
    outbox = await _rows(db_session, OutboxEmail)
    assert len(outbox) == 1
    assert outbox[0].status == "pending"
    assert outbox[0].attempts == 1
    assert outbox[0].last_error is not None


async def test_resend_verification_respects_cooldown(
    client, db_session, email_provider
) -> None:
    await register(client)
    assert len(email_provider.sent) == 1

    await client.post(
        "/api/v1/auth/resend-verification", json={"email": DEFAULT_EMAIL}
    )
    assert len(email_provider.sent) == 1

    pending = (await _rows(db_session, PendingRegistration))[0]
    pending.last_sent_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/resend-verification", json={"email": DEFAULT_EMAIL}
    )

    assert response.status_code == 202
    assert len(email_provider.sent) == 2


async def test_forgot_password_is_generic_for_unknown_email(
    client, email_provider
) -> None:
    response = await client.post(
        FORGOT_URL, json={"email": "nadie@example.com"}
    )

    assert response.status_code == 202
    assert response.json() == {
        "message": "Si el correo corresponde a una cuenta, recibiras un mensaje."
    }
    assert email_provider.sent == []


async def test_reset_password_rejects_weak_password(
    client, email_provider
) -> None:
    await register(client)
    await confirm(client, email_provider)
    await client.post(FORGOT_URL, json={"email": DEFAULT_EMAIL})

    response = await client.post(
        RESET_URL, json={"token": token_from(email_provider), "new_password": "corta"}
    )

    assert response.status_code == 422


async def test_purge_expired_pending_registrations(db_session) -> None:
    db_session.add(
        PendingRegistration(
            email="viejo@example.com",
            name="Viejo",
            password_hash="hash",
            token_hash="token",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    await db_session.commit()

    deleted = await purge_expired_pending_registrations(db_session)

    assert deleted == 1
    assert await _rows(db_session, PendingRegistration) == []


async def test_outbox_retries_and_does_not_duplicate(
    client, db_session, email_provider
) -> None:
    email_provider.fail_next = 1
    await register(client)

    sent = await flush_outbox(db_session, email_provider)

    assert sent == 1
    assert len(email_provider.sent) == 1
    outbox = await _rows(db_session, OutboxEmail)
    assert len(outbox) == 1
    assert outbox[0].status == "sent"
    assert outbox[0].attempts == 2
    assert outbox[0].sent_at is not None
