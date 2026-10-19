from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    app_name: str = "Mi Dinero API"
    environment: str = "development"
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    database_url: str
    test_database_url: str | None = None

    secret_key: str = "change-me"
    field_encryption_key: str = "change-me"

    email_provider: str = "smtp"
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    email_provider_api_key: str = "change-me"
    email_from: str = "no-reply@example.invalid"
    email_verification_ttl_hours: int = 24
    password_reset_ttl_hours: int = 1
    session_ttl_hours: int = 720
    resend_cooldown_seconds: int = 60

    session_cookie_name: str = "mi_dinero_session"
    csrf_cookie_name: str = "mi_dinero_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    rate_limit_login: int = 10
    rate_limit_register: int = 5
    rate_limit_resend: int = 3
    rate_limit_forgot: int = 3
    rate_limit_window_seconds: int = 3600

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def _ensure_async_driver(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
