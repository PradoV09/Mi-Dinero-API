import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        Index("ix_accounts_user_id_is_archived", "user_id", "is_archived"),
        Index(
            "uq_accounts_user_active_name",
            "user_id",
            "name_fingerprint",
            unique=True,
            postgresql_where=text("is_archived = false"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    account_type_code: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("account_types.code", ondelete="RESTRICT"),
        nullable=False,
    )
    currency_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=False,
    )
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
