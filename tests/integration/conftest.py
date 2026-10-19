from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.deps import get_db, get_email_provider
from app.core.config import settings
from app.core.rate_limit import rate_limiter
from app.main import app
from app.services.email import MemoryEmailProvider
from tests.conftest import run_alembic

PROTECTED_TABLES = {"alembic_version", "currencies", "account_types"}


def _database_name(url: str) -> str:
    return make_url(url).database or ""


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = settings.test_database_url
    if not url:
        pytest.fail("TEST_DATABASE_URL no esta definido")
    name = _database_name(url)
    if "test" not in name:
        pytest.fail(f"TEST_DATABASE_URL debe apuntar a una BD de pruebas, no '{name}'")
    if name == _database_name(settings.database_url):
        pytest.fail("TEST_DATABASE_URL no puede ser la misma BD que DATABASE_URL")
    return url


@pytest.fixture(scope="session", autouse=True)
def migrated_database(test_database_url: str) -> None:
    run_alembic("upgrade", "head", test_database_url)


@pytest_asyncio.fixture
async def engine(test_database_url: str) -> AsyncIterator:
    eng = create_async_engine(test_database_url, poolclass=NullPool)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def email_provider() -> MemoryEmailProvider:
    return MemoryEmailProvider()


@pytest_asyncio.fixture
async def client(
    engine, email_provider: MemoryEmailProvider
) -> AsyncIterator[httpx.AsyncClient]:
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_email_provider] = lambda: email_provider
    rate_limiter.reset()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(autouse=True)
async def clean_database(engine) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        rows = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public'"
            )
        )
        tables = [row[0] for row in rows if row[0] not in PROTECTED_TABLES]
        if tables:
            quoted = ", ".join(f'"{table}"' for table in tables)
            await conn.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
    yield
