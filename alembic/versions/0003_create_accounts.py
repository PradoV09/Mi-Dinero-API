"""create accounts and account types

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACCOUNT_TYPES = [
    ("bank", "Cuenta bancaria", 1),
    ("savings", "Ahorros", 2),
    ("debit_card", "Tarjeta debito", 3),
    ("credit_card", "Tarjeta credito", 4),
    ("digital_wallet", "Billetera digital", 5),
    ("cash", "Efectivo", 6),
    ("other", "Otra", 7),
]


def upgrade() -> None:
    account_types = op.create_table(
        "account_types",
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("code", name="pk_account_types"),
    )
    op.bulk_insert(
        account_types,
        [
            {"code": code, "name": name, "sort_order": order}
            for code, name, order in ACCOUNT_TYPES
        ],
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_fingerprint", sa.String(64), nullable=False),
        sa.Column("account_type_code", sa.String(32), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column(
            "opening_balance",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_accounts_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_type_code"],
            ["account_types.code"],
            name="fk_accounts_account_type_code_account_types",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_accounts_currency_code_currencies",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
    )
    op.create_index(
        "ix_accounts_user_id_is_archived",
        "accounts",
        ["user_id", "is_archived"],
    )
    op.create_index(
        "uq_accounts_user_active_name",
        "accounts",
        ["user_id", "name_fingerprint"],
        unique=True,
        postgresql_where=sa.text("is_archived = false"),
    )


def downgrade() -> None:
    op.drop_index("uq_accounts_user_active_name", table_name="accounts")
    op.drop_index("ix_accounts_user_id_is_archived", table_name="accounts")
    op.drop_table("accounts")
    op.drop_table("account_types")
