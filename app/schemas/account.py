from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.money import is_within_range

ACCOUNT_NAME_MAX_LENGTH = 120


def _clean_name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("El nombre de la cuenta no puede estar vacio")
    return cleaned


def _normalize_code(value: str) -> str:
    return value.strip()


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=ACCOUNT_NAME_MAX_LENGTH)
    account_type: str = Field(min_length=1, max_length=32)
    currency_code: str = Field(min_length=3, max_length=3)
    opening_balance: Decimal = Decimal("0")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _clean_name(value)

    @field_validator("account_type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        return _normalize_code(value)

    @field_validator("currency_code")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("opening_balance")
    @classmethod
    def _validate_opening_balance(cls, value: Decimal) -> Decimal:
        if not is_within_range(value):
            raise ValueError("El saldo inicial esta fuera de rango")
        return value


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=ACCOUNT_NAME_MAX_LENGTH)
    account_type: str | None = Field(default=None, min_length=1, max_length=32)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        return _clean_name(value) if value is not None else None

    @field_validator("account_type")
    @classmethod
    def _validate_type(cls, value: str | None) -> str | None:
        return _normalize_code(value) if value is not None else None

    @field_validator("currency_code")
    @classmethod
    def _validate_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @model_validator(mode="after")
    def _require_change(self) -> "AccountUpdate":
        if not self.model_fields_set:
            raise ValueError("Debes enviar al menos un campo para actualizar")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser nulos")
        return self


class AccountResponse(BaseModel):
    id: UUID
    name: str
    account_type: str
    currency_code: str
    opening_balance: str
    balance: str
    is_archived: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BalanceByCurrency(BaseModel):
    currency_code: str
    balance: str


class AccountListResponse(BaseModel):
    items: list[AccountResponse]
    page: int
    page_size: int
    total: int
    balances: list[BalanceByCurrency]
