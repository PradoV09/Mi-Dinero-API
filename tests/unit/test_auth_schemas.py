import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    RegisterRequest,
    normalize_email,
    validate_password,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  ANA@Example.COM ", "ana@example.com"),
        ("a@b.co", "a@b.co"),
    ],
)
def test_normalize_email(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["sin-arroba", "a@b", "@b.com", "a b@c.com", "", "a" * 320 + "@x.com"],
)
def test_normalize_email_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_email(raw)


@pytest.mark.parametrize("password", ["corta", "", "a" * 129])
def test_validate_password_rejects_invalid(password: str) -> None:
    with pytest.raises(ValueError):
        validate_password(password)


def test_register_request_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="malo", name="Ana", password="secreto123")


def test_register_request_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="ana@example.com", name="Ana", password="corta")


def test_register_request_accepts_and_normalizes() -> None:
    request = RegisterRequest(
        email="  Ana@Example.com ", name="  Ana  ", password="secreto123"
    )

    assert request.email == "ana@example.com"
    assert request.name == "Ana"
