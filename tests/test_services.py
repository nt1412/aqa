import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_db_connection(session):
    result = await session.execute(text("SELECT 1"))
    assert result.scalar() == 1


def test_all_tables_registered():
    from app.models.base import Base

    names = set(Base.metadata.tables.keys())
    expected = {
        "projects",
        "test_suites",
        "keywords",
        "platforms",
        "test_cases",
        "test_case_versions",
        "test_steps",
        "executions",
        "execution_steps",
        "users",
        "roles",
        "assignments",
        "test_plans",
        "builds",
        "execution_claims",
        "claim_verifications",
        "req_specs",
        "requirements",
    }
    missing = expected - names
    assert not missing, f"missing tables: {missing}"
