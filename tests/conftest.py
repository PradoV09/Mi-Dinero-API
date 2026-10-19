import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

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

from app.core.config import settings

PROJECT_DIR = Path(__file__).resolve().parents[1]
PROTECTED_TABLES = {"alembic_version", "currencies"}


def run_alembic(action: str, revision: str, database_url: str) -> None:
    env = {**os.environ, "ALEMBIC_DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"alembic {action} {revision} fallo:\n{result.stdout}\n{result.stderr}"
        )


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
