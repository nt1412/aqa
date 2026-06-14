import pytest

from app.schemas.project import ProjectCreate
from app.schemas.suite import SuiteCreate
from app.schemas.testcase import StepIn, TestCaseCreate, VersionCreate
from app.services import projects, suites, testcases


async def _project_and_suite(session, prefix):
    p = await projects.create_project(session, ProjectCreate(name="P", prefix=prefix))
    s = await suites.create_suite(session, p.id, SuiteCreate(name="Suite"))
    return p, s


@pytest.mark.asyncio
async def test_create_test_case_makes_version_and_steps(session):
    p, s = await _project_and_suite(session, "TC1")
    tc = await testcases.create_test_case(
        session,
        s.id,
        TestCaseCreate(
            name="Login works",
            summary="user can log in",
            steps=[StepIn(action="enter creds", expected_result="logged in")],
        ),
    )
    assert tc.external_id == "TC1-1"
    full = await testcases.get_test_case(session, tc.id)
    assert full.current_version.version == 1
    assert len(full.current_version.steps) == 1
    assert full.current_version.steps[0].step_number == 1


@pytest.mark.asyncio
async def test_external_id_increments(session):
    p, s = await _project_and_suite(session, "TC2")
    a = await testcases.create_test_case(session, s.id, TestCaseCreate(name="a"))
    b = await testcases.create_test_case(session, s.id, TestCaseCreate(name="b"))
    assert a.external_id == "TC2-1"
    assert b.external_id == "TC2-2"


@pytest.mark.asyncio
async def test_create_version_clones_and_increments(session):
    p, s = await _project_and_suite(session, "TC3")
    tc = await testcases.create_test_case(
        session,
        s.id,
        TestCaseCreate(name="v", steps=[StepIn(action="a1")]),
    )
    v2 = await testcases.create_version(
        session, tc.id, VersionCreate(summary="updated", steps=[StepIn(action="a2")])
    )
    assert v2.version == 2
    assert v2.summary == "updated"
    full = await testcases.get_test_case(session, tc.id)
    assert full.current_version.version == 2  # latest active version is current


@pytest.mark.asyncio
async def test_get_by_external_id(session):
    p, s = await _project_and_suite(session, "TC4")
    await testcases.create_test_case(session, s.id, TestCaseCreate(name="x"))
    found = await testcases.get_by_external_id(session, p.id, "TC4-1")
    assert found.name == "x"


@pytest.mark.asyncio
async def test_search_test_cases(session):
    p, s = await _project_and_suite(session, "TC5")
    await testcases.create_test_case(session, s.id, TestCaseCreate(name="payment flow"))
    await testcases.create_test_case(session, s.id, TestCaseCreate(name="login flow"))
    results = await testcases.search_test_cases(session, p.id, "payment")
    assert len(results) == 1
    assert results[0].name == "payment flow"


@pytest.mark.asyncio
async def test_endpoints(client, auth_headers):
    pc = await client.post(
        "/api/v1/projects", json={"name": "E", "prefix": "TCE"}, headers=auth_headers
    )
    pid = pc.json()["id"]
    sc = await client.post(
        f"/api/v1/projects/{pid}/suites", json={"name": "S"}, headers=auth_headers
    )
    sid = sc.json()["id"]
    cc = await client.post(
        f"/api/v1/suites/{sid}/cases",
        json={"name": "case", "steps": [{"action": "do", "expected_result": "done"}]},
        headers=auth_headers,
    )
    assert cc.status_code == 201
    cid = cc.json()["id"]
    got = await client.get(f"/api/v1/cases/{cid}", headers=auth_headers)
    assert got.json()["current_version"]["steps"][0]["action"] == "do"
