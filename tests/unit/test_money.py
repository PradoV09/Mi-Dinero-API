from decimal import Decimal

import pytest

from app.core.money import format_amount, has_valid_scale, is_within_range


@pytest.mark.parametrize(
    ("value", "minor_units", "expected"),
    [
        (Decimal("1000"), 2, "1000.00"),
        (Decimal("1000.0000"), 2, "1000.00"),
        (Decimal("20.5"), 2, "20.50"),
        (Decimal("0.005"), 2, "0.01"),
        (Decimal("1"), 0, "1"),
        (Decimal("-12.3456"), 4, "-12.3456"),
    ],
)
def test_format_amount(value, minor_units, expected) -> None:
    assert format_amount(value, minor_units) == expected


@pytest.mark.parametrize(
    ("value", "minor_units", "expected"),
    [
        (Decimal("10.50"), 2, True),
        (Decimal("10.5"), 2, True),
        (Decimal("10.555"), 2, False),
        (Decimal("10.5555"), 4, True),
        (Decimal("10.5"), 0, False),
    ],
)
def test_has_valid_scale(value, minor_units, expected) -> None:
    assert has_valid_scale(value, minor_units) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("0"), True),
        (Decimal("99999999999999.9999"), True),
        (Decimal("100000000000000"), False),
        (Decimal("-100000000000000"), False),
        (Decimal("NaN"), False),
        (Decimal("Infinity"), False),
    ],
)
def test_is_within_range(value, expected) -> None:
    assert is_within_range(value) is expected
