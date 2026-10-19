from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

TransactionType = Literal["income", "expense"]


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: TransactionType
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("El nombre de la categoria no puede estar vacio")
        return cleaned


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    type: TransactionType
    is_system: bool


class CategoryListResponse(BaseModel):
    items: list[CategoryResponse]
    page: int
    page_size: int
    total: int
