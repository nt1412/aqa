"""B2: prove the Alembic chain builds the full current schema from scratch.

Catches the class of bug the test harness can't (it uses Base.metadata.create_all,
not migrations): a model column/table added without a matching migration. Applies
every migration to a throwaway database and asserts the result matches the models
— plus that the compute-on-read view exists.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  register all tables
from app.models.base import Base

REPO_ROOT = Path(__file__).resolve().parent.parent
MIG_DB = "aqa_migtest"
ADMIN_URL = "postgresql+asyncpg://aqa:aqa@localhost:5432/aqa"
MIG_URL = f"postgresql+asyncpg://aqa:aqa@localhost:5432/{MIG_DB}"


@pytest.mark.asyncio
async def test_migrations_build_full_schema_from_scratch():
    # fresh throwaway DB + pgvector (a migration adds a Vector column)
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {MIG_DB}"))
        await conn.execute(text(f"CREATE DATABASE {MIG_DB}"))
    await admin.dispose()
    seed = create_async_engine(MIG_URL, isolation_level="AUTOCOMMIT")
    async with seed.connect() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await seed.dispose()

    try:
        # run the real Alembic env against the throwaway DB, from scratch
        proc = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT,
            env={**os.environ, "DATABASE_URL": MIG_URL},
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"alembic upgrade failed:\n{proc.stderr}"

        eng = create_async_engine(MIG_URL)
        async with eng.connect() as conn:
            tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
            views = await conn.run_sync(lambda c: set(inspect(c).get_view_names()))
            cols = {}
            for t in Base.metadata.tables:
                if t in tables:
                    cols[t] = await conn.run_sync(
                        lambda c, t=t: {col["name"] for col in inspect(c).get_columns(t)}
                    )
        await eng.dispose()

        # every model table + column must have been produced by a migration
        missing_tables = [t for t in Base.metadata.tables if t not in tables]
        assert not missing_tables, f"tables missing from migrations: {missing_tables}"
        missing_cols = [
            f"{t}.{col.name}"
            for t, table in Base.metadata.tables.items()
            for col in table.columns
            if col.name not in cols.get(t, set())
        ]
        assert not missing_cols, f"columns missing from migrations: {missing_cols}"
        # the compute-on-read view is created by a migration too
        assert "latest_result_per_build_case" in views
    finally:
        admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
        async with admin.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {MIG_DB}"))
        await admin.dispose()
