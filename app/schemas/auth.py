import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or " " in email or len(email) > 320:
        raise ValueError("correo invalido")
    local, _, domain = email.partition("@")
    if not local or "." not in domain:
        raise ValueError("correo invalido")
    return email


def validate_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("la contrasena debe tener al menos 8 caracteres")
    if len(value) > 128:
        raise ValueError("la contrasena es demasiado larga")
    return value


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        name = value.strip()
        if not name or len(name) > 120:
            raise ValueError("nombre invalido")
        return name

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        return validate_password(value)


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)


class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, value: str) -> str:
        return validate_password(value)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    created_at: datetime


class MessageResponse(BaseModel):
    message: str
