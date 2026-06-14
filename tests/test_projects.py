import pytest

from app.schemas.project import ProjectCreate
from app.services import projects
from app.services.errors import Conflict, NotFound


@pytest.mark.asyncio
async def test_create_and_get_project(session):
    p = await projects.create_project(session, ProjectCreate(name="Demo", prefix="DEMO"))
    assert p.id is not None
    fetched = await projects.get_project(session, p.id)
    assert fetched.name == "Demo"


@pytest.mark.asyncio
async def test_duplicate_prefix_conflicts(session):
    await projects.create_project(session, ProjectCreate(name="A", prefix="DUP"))
    with pytest.raises(Conflict):
        await projects.create_project(session, ProjectCreate(name="B", prefix="DUP"))


@pytest.mark.asyncio
async def test_get_missing_raises(session):
    with pytest.raises(NotFound):
        await projects.get_project(session, 99999)


@pytest.mark.asyncio
async def test_project_endpoints(client, auth_headers):
    create = await client.post(
        "/api/v1/projects", json={"name": "Web", "prefix": "WEB"}, headers=auth_headers
    )
    assert create.status_code == 201
    pid = create.json()["id"]
    listed = await client.get("/api/v1/projects", headers=auth_headers)
    assert any(p["id"] == pid for p in listed.json())
    got = await client.get(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert got.json()["prefix"] == "WEB"
