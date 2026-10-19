import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_field, encrypt_field
from app.core.errors import ApiError
from app.models import IdempotencyKey

IDEMPOTENCY_TTL = timedelta(hours=24)
IDEMPOTENCY_MAX_KEY_LENGTH = 128


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_request_hash(
    user_id: uuid.UUID, method: str, path: str, payload: dict[str, Any]
) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    )
    material = f"{user_id}|{method.upper()}|{path}|{canonical}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def validate_key(key: str | None) -> str:
    if key is None or not key.strip():
        raise ApiError(
            400,
            "idempotency_key_required",
            "El header Idempotency-Key es obligatorio",
        )
    cleaned = key.strip()
    if len(cleaned) > IDEMPOTENCY_MAX_KEY_LENGTH:
        raise ApiError(
            400,
            "invalid_idempotency_key",
            "El header Idempotency-Key es demasiado largo",
        )
    return cleaned


async def _find(
    session: AsyncSession, user_id: uuid.UUID, key: str
) -> IdempotencyKey | None:
    return await session.scalar(
        select(IdempotencyKey)
        .where(IdempotencyKey.user_id == user_id)
        .where(IdempotencyKey.key == key)
    )


async def reserve_idempotency(
    session: AsyncSession,
    user_id: uuid.UUID,
    key: str,
    method: str,
    path: str,
    payload: dict[str, Any],
) -> IdempotencyKey:
    request_hash = build_request_hash(user_id, method, path, payload)
    record = await _find(session, user_id, key)

    if record is not None and record.expires_at <= _now():
        await session.delete(record)
        await session.flush()
        record = None

    if record is not None:
        if record.request_hash != request_hash:
            raise ApiError(
                409,
                "idempotency_key_reused",
                "Idempotency-Key ya fue usado con otra solicitud",
            )
        if record.response_body is None:
            raise ApiError(
                409,
                "idempotency_key_in_progress",
                "La solicitud con este Idempotency-Key esta en proceso",
            )
        return record

    record = IdempotencyKey(
        user_id=user_id,
        key=key,
        method=method.upper(),
        path=path,
        request_hash=request_hash,
        expires_at=_now() + IDEMPOTENCY_TTL,
    )
    session.add(record)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        existing = await _find(session, user_id, key)
        if (
            existing is not None
            and existing.request_hash == request_hash
            and existing.response_body is not None
        ):
            return existing
        raise ApiError(
            409,
            "idempotency_key_in_progress",
            "La solicitud con este Idempotency-Key esta en proceso",
        ) from exc
    return record


def finish_idempotency(
    record: IdempotencyKey, status_code: int, body: dict[str, Any]
) -> None:
    record.status_code = status_code
    record.response_body = encrypt_field(
        json.dumps(body, sort_keys=True, separators=(",", ":"))
    )


def replay_idempotency(record: IdempotencyKey) -> dict[str, Any]:
    if record.response_body is None:
        raise ApiError(
            409,
            "idempotency_key_in_progress",
            "La solicitud con este Idempotency-Key esta en proceso",
        )
    return json.loads(decrypt_field(record.response_body))
