"""create currencies table and seed initial currencies

Revision ID: 0001
Revises:
Create Date: 2026-10-19

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "currencies",
        sa.Column("code", sa.CHAR(3), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("minor_units", sa.SmallInteger(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
            "minor_units BETWEEN 0 AND 4",
            name="ck_currencies_minor_units_range",
        ),
        sa.PrimaryKeyConstraint("code", name="pk_currencies"),
    )

    currencies = sa.table(
        "currencies",
        sa.column("code", sa.CHAR(3)),
        sa.column("name", sa.String(64)),
        sa.column("minor_units", sa.SmallInteger()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        currencies,
        [
            {
                "code": "COP",
                "name": "Peso colombiano",
                "minor_units": 2,
                "is_active": True,
            },
            {
                "code": "USD",
                "name": "Dolar estadounidense",
                "minor_units": 2,
                "is_active": True,
            },
            {
                "code": "EUR",
                "name": "Euro",
                "minor_units": 2,
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("currencies")
