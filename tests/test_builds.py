import pytest

from app.schemas.plan import BuildCreate, PlanCreate
from app.schemas.project import ProjectCreate
from app.services import builds, plans, projects
from app.services.errors import NotFound


async def _plan(session, prefix):
    p = await projects.create_project(session, ProjectCreate(name="P", prefix=prefix))
    plan = await plans.create_plan(session, p.id, PlanCreate(name="Plan"))
    return plan


@pytest.mark.asyncio
async def test_create_build(session):
    plan = await _plan(session, "B1")
    b = await builds.create_build(session, plan.id, BuildCreate(name="v1", commit_id="abc"))
    assert b.id is not None
    assert b.commit_id == "abc"


@pytest.mark.asyncio
async def test_create_build_is_find_or_create(session):
    plan = await _plan(session, "B2")
    b1 = await builds.create_build(session, plan.id, BuildCreate(name="v1"))
    b2 = await builds.create_build(session, plan.id, BuildCreate(name="v1", commit_id="def"))
    assert b2.id == b1.id  # same (plan, name) -> same build
    assert b2.commit_id == "def"  # commit_id backfilled


@pytest.mark.asyncio
async def test_create_build_unknown_plan(session):
    with pytest.raises(NotFound):
        await builds.create_build(session, 9999, BuildCreate(name="v1"))


@pytest.mark.asyncio
async def test_list_builds(session):
    plan = await _plan(session, "B3")
    await builds.create_build(session, plan.id, BuildCreate(name="v1"))
    await builds.create_build(session, plan.id, BuildCreate(name="v2"))
    rows = await builds.list_builds(session, plan.id)
    assert {b.name for b in rows} == {"v1", "v2"}


@pytest.mark.asyncio
async def test_build_endpoints(client, auth_headers):
    pc = await client.post(
        "/api/v1/projects", json={"name": "P", "prefix": "BE"}, headers=auth_headers
    )
    pid = pc.json()["id"]
    plan = await client.post(
        f"/api/v1/projects/{pid}/plans", json={"name": "Plan"}, headers=auth_headers
    )
    plan_id = plan.json()["id"]
    create = await client.post(
        f"/api/v1/plans/{plan_id}/builds", json={"name": "v1", "tag": "1.0"}, headers=auth_headers
    )
    assert create.status_code == 201
    listed = await client.get(f"/api/v1/plans/{plan_id}/builds", headers=auth_headers)
    assert any(b["name"] == "v1" for b in listed.json())
