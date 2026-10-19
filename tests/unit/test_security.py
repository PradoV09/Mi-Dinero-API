import pytest

from app.core.security import (
    constant_time_equals,
    generate_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)


def test_hash_password_uses_argon2id() -> None:
    hashed = hash_password("secreto123")

    assert hashed.startswith("$argon2id$")
    assert "secreto123" not in hashed


def test_verify_password_accepts_correct_and_rejects_wrong() -> None:
    hashed = hash_password("secreto123")

    assert verify_password("secreto123", hashed) is True
    assert verify_password("otra", hashed) is False
    assert verify_password("secreto123", "no-es-un-hash") is False


def test_hash_password_is_salted() -> None:
    assert hash_password("secreto123") != hash_password("secreto123")


def test_password_needs_rehash_is_false_for_current_params() -> None:
    assert password_needs_rehash(hash_password("secreto123")) is False


def test_generate_token_is_random_and_url_safe() -> None:
    first = generate_token()
    second = generate_token()

    assert first != second
    assert len(first) >= 32


def test_hash_token_is_stable_sha256() -> None:
    token = generate_token()
    digest = hash_token(token)

    assert digest == hash_token(token)
    assert len(digest) == 64
    assert all(character in "0123456789abcdef" for character in digest)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [("abc", "abc", True), ("abc", "abd", False), ("abc", "abcd", False)],
)
def test_constant_time_equals(left: str, right: str, expected: bool) -> None:
    assert constant_time_equals(left, right) is expected
