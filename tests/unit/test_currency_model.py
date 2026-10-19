from sqlalchemy import CheckConstraint

from app.db.base import Base
from app.models import Currency

EXPECTED_COLUMNS = {
    "code",
    "name",
    "minor_units",
    "is_active",
    "created_at",
    "updated_at",
}


def test_table_name() -> None:
    assert Currency.__tablename__ == "currencies"


def test_columns_match_schema() -> None:
    assert {column.name for column in Currency.__table__.columns} == EXPECTED_COLUMNS


def test_primary_key_uses_naming_convention() -> None:
    assert Currency.__table__.primary_key.name == "pk_currencies"


def test_primary_key_columns() -> None:
    assert [column.name for column in Currency.__table__.primary_key] == ["code"]


def test_minor_units_check_constraint() -> None:
    checks = [
        constraint
        for constraint in Currency.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    ]

    assert len(checks) == 1
    assert "minor_units BETWEEN 0 AND 4" in str(checks[0].sqltext)
    assert checks[0].name == "ck_currencies_minor_units_range"


def test_currency_code_length_is_three() -> None:
    assert Currency.__table__.c.code.type.length == 3


def test_timestamps_are_timezone_aware() -> None:
    assert Currency.__table__.c.created_at.type.timezone is True
    assert Currency.__table__.c.updated_at.type.timezone is True


def test_is_active_defaults_to_true() -> None:
    default = Currency.__table__.c.is_active.server_default

    assert default is not None
    assert "true" in str(default.arg).lower()


def test_metadata_naming_convention_present() -> None:
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
