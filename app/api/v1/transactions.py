import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_csrf
from app.core.crypto import decrypt_field, encrypt_field
from app.core.errors import ApiError
from app.core.money import format_amount, has_valid_scale
from app.models import Account, Category, Currency, Transaction, User
from app.schemas.category import TransactionType
from app.schemas.transaction import (
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdate,
)
from app.services.idempotency import (
    finish_idempotency,
    replay_idempotency,
    reserve_idempotency,
    validate_key,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _serialize(
    transaction: Transaction, category_name: str, currency: Currency
) -> TransactionResponse:
    return TransactionResponse(
        id=transaction.id,
        type=transaction.type,
        account_id=transaction.account_id,
        category_id=transaction.category_id,
        category_name=category_name,
        amount=format_amount(transaction.amount, currency.minor_units),
        currency_code=currency.code,
        transaction_date=transaction.transaction_date,
        description=(
            decrypt_field(transaction.description)
            if transaction.description is not None
            else None
        ),
        created_at=transaction.created_at,
        updated_at=transaction.updated_at,
    )


async def _owned_transaction(
    session: AsyncSession, user: User, transaction_id: uuid.UUID
) -> Transaction:
    transaction = await session.scalar(
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .where(Transaction.user_id == user.id)
    )
    if transaction is None:
        raise ApiError(
            404, "transaction_not_found", "Movimiento no encontrado"
        )
    return transaction


async def _resolve_account(
    session: AsyncSession,
    user: User,
    account_id: uuid.UUID,
    require_active: bool,
) -> Account:
    account = await session.scalar(
        select(Account)
        .where(Account.id == account_id)
        .where(Account.user_id == user.id)
    )
    if account is None:
        raise ApiError(404, "account_not_found", "Cuenta no encontrada")
    if require_active and account.is_archived:
        raise ApiError(
            409, "account_archived", "No puedes usar una cuenta archivada"
        )
    return account


async def _resolve_category(
    session: AsyncSession, user: User, category_id: uuid.UUID
) -> Category:
    category = await session.scalar(
        select(Category)
        .where(Category.id == category_id)
        .where(
            (Category.user_id.is_(None)) | (Category.user_id == user.id)
        )
    )
    if category is None:
        raise ApiError(404, "category_not_found", "Categoria no encontrada")
    return category


async def _currency(session: AsyncSession, account: Account) -> Currency:
    currency = await session.get(Currency, account.currency_code)
    if currency is None:
        raise ApiError(
            500, "currency_missing", "Moneda de la cuenta no disponible"
        )
    return currency


def _validate(
    transaction_type: TransactionType,
    category: Category,
    amount: Decimal,
    currency: Currency,
) -> None:
    if category.type != transaction_type:
        raise ApiError(
            422,
            "category_type_mismatch",
            "La categoria no corresponde al tipo de movimiento",
        )
    if not has_valid_scale(amount, currency.minor_units):
        raise ApiError(
            422,
            "invalid_amount_scale",
            f"El importe admite como maximo {currency.minor_units} decimales",
        )

@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    transaction_type: TransactionType | None = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TransactionListResponse:
    if from_date is not None and to_date is not None and from_date > to_date:
        raise ApiError(
            422, "invalid_date_range", "La fecha inicial no puede superar la final"
        )

    filters = [Transaction.user_id == user.id]
    if from_date is not None:
        filters.append(Transaction.transaction_date >= from_date)
    if to_date is not None:
        filters.append(Transaction.transaction_date <= to_date)
    if account_id is not None:
        filters.append(Transaction.account_id == account_id)
    if category_id is not None:
        filters.append(Transaction.category_id == category_id)
    if transaction_type is not None:
        filters.append(Transaction.type == transaction_type)

    total = await session.scalar(
        select(func.count()).select_from(Transaction).where(*filters)
    )
    rows = (
        await session.execute(
            select(
                Transaction,
                Category.name,
                Currency,
            )
            .join(Category, Category.id == Transaction.category_id)
            .join(Account, Account.id == Transaction.account_id)
            .join(Currency, Currency.code == Account.currency_code)
            .where(*filters)
            .order_by(
                Transaction.transaction_date.desc(),
                Transaction.created_at.desc(),
                Transaction.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    return TransactionListResponse(
        items=[
            _serialize(transaction, category_name, currency)
            for transaction, category_name, currency in rows
        ],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


@router.post("", status_code=201, response_model=TransactionResponse)
async def create_transaction(
    payload: TransactionCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_csrf),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    key = validate_key(idempotency_key)
    record = await reserve_idempotency(
        session,
        user.id,
        key,
        "POST",
        request.url.path,
        payload.model_dump(mode="json"),
    )
    if record.response_body is not None:
        return JSONResponse(
            status_code=record.status_code or 200,
            content=replay_idempotency(record),
        )

    account = await _resolve_account(
        session, user, payload.account_id, require_active=True
    )
    category = await _resolve_category(session, user, payload.category_id)
    currency = await _currency(session, account)
    _validate(payload.type, category, payload.amount, currency)

    transaction = Transaction(
        user_id=user.id,
        account_id=account.id,
        category_id=category.id,
        type=payload.type,
        amount=payload.amount,
        transaction_date=payload.transaction_date,
        description=(
            encrypt_field(payload.description)
            if payload.description is not None
            else None
        ),
    )
    session.add(transaction)
    await session.flush()
    await session.refresh(transaction)

    body = _serialize(transaction, category.name, currency).model_dump(
        mode="json"
    )
    finish_idempotency(record, 201, body)
    await session.commit()
    return JSONResponse(status_code=201, content=body)


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_csrf),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    key = validate_key(idempotency_key)
    record = await reserve_idempotency(
        session,
        user.id,
        key,
        "PATCH",
        request.url.path,
        payload.model_dump(exclude_unset=True, mode="json"),
    )
    if record.response_body is not None:
        return JSONResponse(
            status_code=record.status_code or 200,
            content=replay_idempotency(record),
        )

    transaction = await _owned_transaction(session, user, transaction_id)
    changes = payload.model_dump(exclude_unset=True)

    if "account_id" in changes:
        account = await _resolve_account(
            session, user, changes["account_id"], require_active=True
        )
    else:
        account = await session.get(Account, transaction.account_id)
        if account is None:
            raise ApiError(404, "account_not_found", "Cuenta no encontrada")

    if "category_id" in changes:
        category = await _resolve_category(
            session, user, changes["category_id"]
        )
    else:
        category = await session.get(Category, transaction.category_id)
        if category is None:
            raise ApiError(
                404, "category_not_found", "Categoria no encontrada"
            )

    transaction_type = changes.get("type", transaction.type)
    amount = changes.get("amount", transaction.amount)
    currency = await _currency(session, account)
    _validate(transaction_type, category, amount, currency)

    transaction.type = transaction_type
    transaction.account_id = account.id
    transaction.category_id = category.id
    transaction.amount = amount
    if "transaction_date" in changes:
        transaction.transaction_date = changes["transaction_date"]
    if "description" in changes:
        transaction.description = (
            encrypt_field(changes["description"])
            if changes["description"] is not None
            else None
        )

    await session.flush()
    await session.refresh(transaction)

    body = _serialize(transaction, category.name, currency).model_dump(
        mode="json"
    )
    finish_idempotency(record, 200, body)
    await session.commit()
    return JSONResponse(status_code=200, content=body)


@router.delete("/{transaction_id}", status_code=204)
async def delete_transaction(
    transaction_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: None = Depends(require_csrf),
) -> Response:
    transaction = await _owned_transaction(session, user, transaction_id)
    await session.delete(transaction)
    await session.commit()
    return Response(status_code=204)
