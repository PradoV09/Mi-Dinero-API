from decimal import ROUND_HALF_UP, Decimal

MAX_ABS_AMOUNT = Decimal(10) ** 14


def amount_step(minor_units: int) -> Decimal:
    return Decimal(1).scaleb(-minor_units)


def format_amount(value: Decimal, minor_units: int) -> str:
    return format(value.quantize(amount_step(minor_units), rounding=ROUND_HALF_UP), "f")


def has_valid_scale(value: Decimal, minor_units: int) -> bool:
    return value == value.quantize(amount_step(minor_units))


def is_finite(value: Decimal) -> bool:
    return value.is_finite()


def is_within_range(value: Decimal) -> bool:
    return is_finite(value) and abs(value) < MAX_ABS_AMOUNT
