import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_LENGTH = 12
KEY_LENGTH = 32


class FieldCryptoError(Exception):
    pass


def _decode_key_material(material: str) -> bytes:
    try:
        padded = material + "=" * (-len(material) % 4)
        decoded = base64.urlsafe_b64decode(padded)
    except Exception:
        decoded = b""
    if len(decoded) == KEY_LENGTH:
        return decoded
    return hashlib.sha256(material.encode("utf-8")).digest()


@dataclass(frozen=True)
class FieldCipher:
    keys: dict[str, bytes]
    current_version: str

    @classmethod
    def from_setting(cls, value: str) -> "FieldCipher":
        entries: list[tuple[str, bytes]] = []
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            version = "v1"
            material = part
            prefix, separator, rest = part.partition(":")
            if separator and prefix.startswith("v") and prefix[1:].isdigit():
                version = prefix
                material = rest
            if not material:
                raise FieldCryptoError("FIELD_ENCRYPTION_KEY tiene una entrada vacia")
            entries.append((version, _decode_key_material(material)))

        if not entries:
            raise FieldCryptoError("FIELD_ENCRYPTION_KEY no esta configurada")
        versions = [version for version, _ in entries]
        if len(set(versions)) != len(versions):
            raise FieldCryptoError("FIELD_ENCRYPTION_KEY tiene versiones duplicadas")
        return cls(keys=dict(entries), current_version=entries[0][0])

    def encrypt(self, plaintext: str) -> str:
        key = self.keys[self.current_version]
        nonce = os.urandom(NONCE_LENGTH)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
        payload = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return f"{self.current_version}:{payload}"

    def decrypt(self, token: str) -> str:
        version, separator, payload = token.partition(":")
        if not separator or version not in self.keys:
            raise FieldCryptoError("Version de cifrado desconocida")
        try:
            raw = base64.urlsafe_b64decode(payload)
        except Exception as exc:
            raise FieldCryptoError("Payload cifrado invalido") from exc
        if len(raw) <= NONCE_LENGTH:
            raise FieldCryptoError("Payload cifrado invalido")
        nonce, ciphertext = raw[:NONCE_LENGTH], raw[NONCE_LENGTH:]
        try:
            plaintext = AESGCM(self.keys[version]).decrypt(nonce, ciphertext, None)
        except InvalidTag as exc:
            raise FieldCryptoError("No se pudo descifrar el campo") from exc
        return plaintext.decode("utf-8")


@lru_cache
def _cipher_for(setting: str) -> FieldCipher:
    return FieldCipher.from_setting(setting)


def get_cipher() -> FieldCipher:
    return _cipher_for(settings.field_encryption_key)


def encrypt_field(plaintext: str) -> str:
    return get_cipher().encrypt(plaintext)


def decrypt_field(token: str) -> str:
    return get_cipher().decrypt(token)


def normalize_account_name(name: str) -> str:
    return " ".join(name.split()).casefold()


def name_fingerprint(name: str) -> str:
    key = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    normalized = normalize_account_name(name)
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_field_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(KEY_LENGTH)).decode("ascii")
