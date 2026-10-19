import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def build(**overrides) -> Settings:
    values = {
        "database_url": "postgresql://user:pass@localhost:5433/mi_dinero",
        "test_database_url": "postgresql://user:pass@localhost:5433/mi_dinero_test",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_plain_postgresql_url_uses_asyncpg_driver() -> None:
    configured = build()

    assert (
        configured.database_url
        == "postgresql+asyncpg://user:pass@localhost:5433/mi_dinero"
    )
    assert (
        configured.test_database_url
        == "postgresql+asyncpg://user:pass@localhost:5433/mi_dinero_test"
    )


def test_async_url_is_not_doubled() -> None:
    configured = build(
        database_url="postgresql+asyncpg://user:pass@localhost:5433/mi_dinero",
        test_database_url=None,
    )

    assert configured.database_url == (
        "postgresql+asyncpg://user:pass@localhost:5433/mi_dinero"
    )
    assert configured.test_database_url is None


def test_non_postgresql_url_is_left_untouched() -> None:
    configured = build(database_url="sqlite+aiosqlite:///local.db")

    assert configured.database_url == "sqlite+aiosqlite:///local.db"


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, test_database_url=None)


@pytest.mark.parametrize(
    ("environment", "expected"),
    [("development", True), ("production", False), ("staging", False)],
)
def test_is_development(environment: str, expected: bool) -> None:
    assert build(environment=environment).is_development is expected


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5433/db")
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()


def test_get_settings_reads_and_normalizes_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5433/db")
    get_settings.cache_clear()
    try:
        assert get_settings().database_url == (
            "postgresql+asyncpg://user:pass@localhost:5433/db"
        )
    finally:
        get_settings.cache_clear()
