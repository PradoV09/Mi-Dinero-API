import pytest

from app.core.crypto import (
    FieldCipher,
    FieldCryptoError,
    decrypt_field,
    encrypt_field,
    generate_field_key,
    name_fingerprint,
    normalize_account_name,
)


def test_encrypt_decrypt_roundtrip_unicode() -> None:
    plaintext = "Cuenta de ahorros ñandú 🐷"

    token = encrypt_field(plaintext)

    assert token != plaintext
    assert token.startswith("v1:")
    assert decrypt_field(token) == plaintext


def test_encrypt_is_randomized() -> None:
    assert encrypt_field("Efectivo") != encrypt_field("Efectivo")


def test_tampered_ciphertext_is_rejected() -> None:
    token = encrypt_field("Efectivo")
    version, payload = token.split(":", 1)
    tampered = f"{version}:{payload[:-4]}AAAA"

    with pytest.raises(FieldCryptoError):
        decrypt_field(tampered)


def test_unknown_version_is_rejected() -> None:
    token = encrypt_field("Efectivo")
    _, payload = token.split(":", 1)

    with pytest.raises(FieldCryptoError):
        decrypt_field(f"v9:{payload}")


def test_key_rotation_decrypts_old_version() -> None:
    old_key = generate_field_key()
    new_key = generate_field_key()
    old = FieldCipher.from_setting(f"v1:{old_key}")
    current = FieldCipher.from_setting(f"v2:{new_key},v1:{old_key}")

    old_token = old.encrypt("Efectivo")

    assert current.decrypt(old_token) == "Efectivo"
    assert current.encrypt("Efectivo").startswith("v2:")
    assert current.decrypt(current.encrypt("Efectivo")) == "Efectivo"


def test_duplicate_versions_are_rejected() -> None:
    key = generate_field_key()

    with pytest.raises(FieldCryptoError):
        FieldCipher.from_setting(f"v1:{key},v1:{key}")


@pytest.mark.parametrize("value", ["", "v1:", ",,"])
def test_empty_setting_is_rejected(value: str) -> None:
    with pytest.raises(FieldCryptoError):
        FieldCipher.from_setting(value)


def test_normalize_account_name_collapses_case_and_spaces() -> None:
    assert normalize_account_name("  Mi   Cuenta  ") == "mi cuenta"
    assert normalize_account_name("MI CUENTA") == "mi cuenta"


def test_name_fingerprint_is_stable_and_sensitive() -> None:
    first = name_fingerprint("Mi Cuenta")
    second = name_fingerprint("  mi   cuenta ")

    assert first == second
    assert first != name_fingerprint("Otra cuenta")
    assert len(first) == 64
