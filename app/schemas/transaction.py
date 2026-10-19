from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.money import is_within_range
from app.schemas.category import TransactionType

DESCRIPTION_MAX_LENGTH = 500


def _validate_amount(value: Decimal) -> Decimal:
    if not is_within_range(value):
        raise ValueError("El importe esta fuera de rango")
    if value <= 0:
        raise ValueError("El importe debe ser mayor que cero")
    return value


def _clean_description(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > DESCRIPTION_MAX_LENGTH:
        raise ValueError(
            f"La descripcion no puede superar {DESCRIPTION_MAX_LENGTH} caracteres"
        )
    return cleaned


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: TransactionType
    account_id: UUID
    category_id: UUID
    amount: Decimal
    transaction_date: date
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)

    @field_validator("amount")
    @classmethod
    def _amount(cls, value: Decimal) -> Decimal:
        return _validate_amount(value)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return _clean_description(value)


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: TransactionType | None = None
    account_id: UUID | None = None
    category_id: UUID | None = None
    amount: Decimal | None = None
    transaction_date: date | None = None
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)

    @field_validator("amount")
    @classmethod
    def _amount(cls, value: Decimal | None) -> Decimal | None:
        return _validate_amount(value) if value is not None else None

    @field_validator("description")
    @classmethod
    def _description(cls, value: str | None) -> str | None:
        return _clean_description(value)

    @model_validator(mode="after")
    def _require_change(self) -> "TransactionUpdate":
        if not self.model_fields_set:
            raise ValueError("Debes enviar al menos un campo para actualizar")
        for field in self.model_fields_set:
            if field != "description" and getattr(self, field) is None:
                raise ValueError("Los campos enviados no pueden ser nulos")
        return self


class TransactionResponse(BaseModel):
    id: UUID
    type: TransactionType
    account_id: UUID
    category_id: UUID
    category_name: str
    amount: str
    currency_code: str
    transaction_date: date
    description: str | None
    created_at: datetime
    updated_at: datetime


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    page: int
    page_size: int
    total: int
