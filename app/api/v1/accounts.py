import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_csrf
from app.core.crypto import decrypt_field, encrypt_field, name_fingerprint
from app.core.errors import ApiError
from app.core.money import format_amount, has_valid_scale, is_within_range
from app.models import Account, AccountType, Currency, User
from app.schemas.account import (
    AccountCreate,
    AccountListResponse,
    AccountResponse,
    AccountUpdate,
    BalanceByCurrency,
)
from app.services.accounts import account_has_transactions

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(account: Account, currency: Currency) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        name=decrypt_field(account.name),
        account_type=account.account_type_code,
        currency_code=account.currency_code,
        opening_balance=format_amount(account.opening_balance, currency.minor_units),
        is_archived=account.is_archived,
        archived_at=account.archived_at,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


async def _owned_account(
    session: AsyncSession, user: User, account_id: uuid.UUID
) -> Account:
    account = await session.scalar(
        select(Account)
        .where(Account.id == account_id)
        .where(Account.user_id == user.id)
    )
    if account is None:
        raise ApiError(404, "account_not_found", "Cuenta no encontrada")
    return account


async def _resolve_type(session: AsyncSession, code: str) -> AccountType:
    account_type = await session.get(AccountType, code)
    if account_type is None:
        raise ApiError(422, "invalid_account_type", "Tipo de cuenta invalido")
    return account_type


async def _resolve_currency(session: AsyncSession, code: str) -> Currency:
    currency = await session.get(Currency, code)
    if currency is None or not currency.is_active:
        raise ApiError(422, "invalid_currency", "Moneda invalida o inactiva")
    return currency


def _validate_opening_balance(
    value: Decimal, currency: Currency, account_type_code: str
) -> None:
    if not is_within_range(value):
        raise ApiError(422, "invalid_amount", "El saldo inicial esta fuera de rango")
    if not has_valid_scale(value, currency.minor_units):
        raise ApiError(
            422,
            "invalid_amount_scale",
            f"El saldo admite como maximo {currency.minor_units} decimales",
        )
    if value < 0 and account_type_code != "credit_card":
        raise ApiError(
            422,
            "negative_opening_balance_not_allowed",
            "Solo las tarjetas de credito admiten saldo inicial negativo",
        )


async def _name_taken(
    session: AsyncSession,
    user_id: uuid.UUID,
    fingerprint: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    statement = (
        select(Account.id)
        .where(Account.user_id == user_id)
        .where(Account.name_fingerprint == fingerprint)
        .where(Account.is_archived.is_(False))
    )
    if exclude_id is not None:
        statement = statement.where(Account.id != exclude_id)
    return await session.scalar(statement) is not None


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    include_archived: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AccountListResponse:
    filters = [Account.user_id == user.id]
    if not include_archived:
        filters.append(Account.is_archived.is_(False))

    total = await session.scalar(
        select(func.count()).select_from(Account).where(*filters)
    )
    accounts = (
        await session.execute(
            select(Account)
            .where(*filters)
            .order_by(Account.created_at.desc(), Account.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    codes = {account.currency_code for account in accounts}
    currencies: dict[str, Currency] = {}
    if codes:
        rows = await session.execute(
            select(Currency).where(Currency.code.in_(codes))
        )
        currencies = {currency.code: currency for currency in rows.scalars()}

    balance_rows = (
        await session.execute(
            select(
                Account.currency_code,
                Currency.minor_units,
                func.sum(Account.opening_balance),
            )
            .join(Currency, Currency.code == Account.currency_code)
            .where(Account.user_id == user.id)
            .where(Account.is_archived.is_(False))
            .group_by(Account.currency_code, Currency.minor_units)
            .order_by(Account.currency_code)
        )
    ).all()

    return AccountListResponse(
        items=[
            _serialize(account, currencies[account.currency_code])
            for account in accounts
        ],
        page=page,
        page_size=page_size,
        total=total or 0,
        balances=[
            BalanceByCurrency(
                currency_code=code,
                balance=format_amount(total_balance or Decimal("0"), minor_units),
            )
            for code, minor_units, total_balance in balance_rows
        ],
    )


@router.post("", status_code=201, response_model=AccountResponse)
async def create_account(
    payload: AccountCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_csrf),
) -> AccountResponse:
    account_type = await _resolve_type(session, payload.account_type)
    currency = await _resolve_currency(session, payload.currency_code)
    _validate_opening_balance(
        payload.opening_balance, currency, account_type.code
    )

    fingerprint = name_fingerprint(payload.name)
    if await _name_taken(session, user.id, fingerprint):
        raise ApiError(
            409, "account_name_taken", "Ya tienes una cuenta activa con ese nombre"
        )

    account = Account(
        user_id=user.id,
        name=encrypt_field(payload.name),
        name_fingerprint=fingerprint,
        account_type_code=account_type.code,
        currency_code=currency.code,
        opening_balance=payload.opening_balance,
    )
    session.add(account)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(
            409, "account_name_taken", "Ya tienes una cuenta activa con ese nombre"
        ) from exc
    await session.refresh(account)
    return _serialize(account, currency)


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AccountResponse:
    account = await _owned_account(session, user, account_id)
    currency = await session.get(Currency, account.currency_code)
    if currency is None:
        raise ApiError(500, "currency_missing", "Moneda de la cuenta no disponible")
    return _serialize(account, currency)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_csrf),
) -> AccountResponse:
    account = await _owned_account(session, user, account_id)
    changes = payload.model_dump(exclude_unset=True)

    new_type_code = changes.get("account_type", account.account_type_code)
    account_type = await _resolve_type(session, new_type_code)

    if "currency_code" in changes and changes["currency_code"] != account.currency_code:
        if await account_has_transactions(session, account.id):
            raise ApiError(
                409,
                "currency_change_not_allowed",
                "No puedes cambiar la moneda de una cuenta con movimientos",
            )
        currency = await _resolve_currency(session, changes["currency_code"])
        _validate_opening_balance(
            account.opening_balance, currency, account_type.code
        )
        account.currency_code = currency.code
    else:
        currency = await session.get(Currency, account.currency_code)
        if currency is None:
            raise ApiError(
                500, "currency_missing", "Moneda de la cuenta no disponible"
            )
        _validate_opening_balance(
            account.opening_balance, currency, account_type.code
        )

    if "name" in changes:
        fingerprint = name_fingerprint(changes["name"])
        if await _name_taken(session, user.id, fingerprint, exclude_id=account.id):
            raise ApiError(
                409,
                "account_name_taken",
                "Ya tienes una cuenta activa con ese nombre",
            )
        account.name = encrypt_field(changes["name"])
        account.name_fingerprint = fingerprint

    if "account_type" in changes:
        account.account_type_code = account_type.code

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(
            409, "account_name_taken", "Ya tienes una cuenta activa con ese nombre"
        ) from exc
    await session.refresh(account)
    return _serialize(account, currency)


@router.post("/{account_id}/archive", response_model=AccountResponse)
async def archive_account(
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_csrf),
) -> AccountResponse:
    account = await _owned_account(session, user, account_id)
    if not account.is_archived:
        account.is_archived = True
        account.archived_at = _now()
        await session.commit()
        await session.refresh(account)

    currency = await session.get(Currency, account.currency_code)
    if currency is None:
        raise ApiError(500, "currency_missing", "Moneda de la cuenta no disponible")
    return _serialize(account, currency)
