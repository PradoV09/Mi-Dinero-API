import asyncio
import uuid

import asyncpg
from sqlalchemy.engine import make_url

from tests.conftest import run_alembic


def _admin_connection_kwargs(url: str) -> dict:
    parsed = make_url(url)
    return {
        "host": parsed.host,
        "port": parsed.port or 5432,
        "user": parsed.username,
        "password": parsed.password,
        "database": "postgres",
    }


async def _create_database(url: str, name: str) -> None:
    conn = await asyncpg.connect(**_admin_connection_kwargs(url))
    try:
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _drop_database(url: str, name: str) -> None:
    conn = await asyncpg.connect(**_admin_connection_kwargs(url))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await conn.close()


async def _table_exists(url: str, database: str, table: str) -> bool:
    parsed = make_url(url)
    conn = await asyncpg.connect(
        host=parsed.host,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        database=database,
    )
    try:
        return bool(
            await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = $1)",
                table,
            )
        )
    finally:
        await conn.close()


async def _count_rows(url: str, database: str, table: str) -> int:
    parsed = make_url(url)
    conn = await asyncpg.connect(
        host=parsed.host,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        database=database,
    )
    try:
        return await conn.fetchval(f'SELECT count(*) FROM "{table}"')
    finally:
        await conn.close()


def test_migrations_upgrade_downgrade_upgrade(test_database_url: str) -> None:
    parsed = make_url(test_database_url)
    temp_db = f"mi_dinero_migration_test_{uuid.uuid4().hex[:8]}"
    temp_url = parsed.set(database=temp_db).render_as_string(hide_password=False)

    try:
        asyncio.run(_create_database(test_database_url, temp_db))

        run_alembic("upgrade", "head", temp_url)
        assert asyncio.run(_table_exists(temp_url, temp_db, "currencies"))
        assert asyncio.run(_count_rows(temp_url, temp_db, "currencies")) == 3

        run_alembic("downgrade", "base", temp_url)
        assert not asyncio.run(_table_exists(temp_url, temp_db, "currencies"))

        run_alembic("upgrade", "head", temp_url)
        assert asyncio.run(_table_exists(temp_url, temp_db, "currencies"))
    finally:
        asyncio.run(_drop_database(test_database_url, temp_db))
