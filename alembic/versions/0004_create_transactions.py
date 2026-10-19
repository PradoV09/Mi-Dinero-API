"""create categories, transactions and idempotency keys

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19

"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYSTEM_CATEGORIES = [
    ("income", "Salario"),
    ("income", "Freelance"),
    ("income", "Inversiones"),
    ("income", "Otros ingresos"),
    ("expense", "Alimentacion"),
    ("expense", "Transporte"),
    ("expense", "Vivienda"),
    ("expense", "Servicios"),
    ("expense", "Salud"),
    ("expense", "Educacion"),
    ("expense", "Entretenimiento"),
    ("expense", "Compras"),
    ("expense", "Otros gastos"),
]


def upgrade() -> None:
    categories = op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(7), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
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
        sa.CheckConstraint(
            "type IN ('income', 'expense')", name="ck_categories_type_valid"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_categories_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
    )
    op.create_index(
        "uq_categories_system_type_name",
        "categories",
        ["type", "name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )
    op.create_index(
        "uq_categories_user_type_name",
        "categories",
        ["user_id", "type", "name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.bulk_insert(
        categories,
        [
            {"id": uuid.uuid4(), "user_id": None, "type": category_type, "name": name}
            for category_type, name in SYSTEM_CATEGORIES
        ],
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(7), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "type IN ('income', 'expense')", name="ck_transactions_type_valid"
        ),
        sa.CheckConstraint(
            "amount > 0", name="ck_transactions_amount_positive"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_transactions_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_transactions_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_transactions_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transactions"),
    )
    op.create_index(
        "ix_transactions_user_date",
        "transactions",
        ["user_id", "transaction_date"],
    )
    op.create_index(
        "ix_transactions_user_account",
        "transactions",
        ["user_id", "account_id"],
    )
    op.create_index(
        "ix_transactions_user_category",
        "transactions",
        ["user_id", "category_id"],
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_idempotency_keys_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_keys"),
        sa.UniqueConstraint(
            "user_id", "key", name="uq_idempotency_keys_user_id_key"
        ),
    )
    op.create_index(
        "ix_idempotency_keys_expires_at",
        "idempotency_keys",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_idempotency_keys_expires_at", table_name="idempotency_keys"
    )
    op.drop_table("idempotency_keys")
    op.drop_index("ix_transactions_user_category", table_name="transactions")
    op.drop_index("ix_transactions_user_account", table_name="transactions")
    op.drop_index("ix_transactions_user_date", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("uq_categories_user_type_name", table_name="categories")
    op.drop_index("uq_categories_system_type_name", table_name="categories")
    op.drop_table("categories")
