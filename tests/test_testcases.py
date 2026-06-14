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
async def test_create_version_clones_steps_and_carries_duration(session):
    p, s = await _project_and_suite(session, "TC6")
    tc = await testcases.create_test_case(
        session,
        s.id,
        TestCaseCreate(name="v", estimated_duration=120, steps=[StepIn(action="a1")]),
    )
    # no steps override -> clone copies the latest version's steps
    v2 = await testcases.create_version(session, tc.id, VersionCreate(summary="upd"))
    assert v2.estimated_duration == 120
    assert [st.action for st in v2.steps] == ["a1"]
    assert v2.steps[0].step_number == 1


@pytest.mark.asyncio
async def test_create_version_endpoint(client, auth_headers):
    pc = await client.post(
        "/api/v1/projects", json={"name": "VE", "prefix": "VEP"}, headers=auth_headers
    )
    pid = pc.json()["id"]
    sc = await client.post(
        f"/api/v1/projects/{pid}/suites", json={"name": "S"}, headers=auth_headers
    )
    cc = await client.post(
        f"/api/v1/suites/{sc.json()['id']}/cases",
        json={"name": "c", "steps": [{"action": "step one"}]},
        headers=auth_headers,
    )
    cid = cc.json()["id"]
    resp = await client.post(
        f"/api/v1/cases/{cid}/versions",
        json={"summary": "v2 summary"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 2
    assert body["steps"][0]["action"] == "step one"


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


@pytest.mark.asyncio
async def test_list_cases_in_suite(session):
    p, s = await _project_and_suite(session, "LCS")
    await testcases.create_test_case(session, s.id, TestCaseCreate(name="a"))
    await testcases.create_test_case(session, s.id, TestCaseCreate(name="b"))
    rows = await testcases.list_cases_in_suite(session, s.id)
    assert [r.name for r in rows] == ["a", "b"]
    assert rows[0].current_version is not None


@pytest.mark.asyncio
async def test_list_cases_in_suite_endpoint(client, auth_headers):
    pc = await client.post(
        "/api/v1/projects", json={"name": "P", "prefix": "LCE"}, headers=auth_headers
    )
    pid = pc.json()["id"]
    sc = await client.post(
        f"/api/v1/projects/{pid}/suites", json={"name": "S"}, headers=auth_headers
    )
    sid = sc.json()["id"]
    await client.post(f"/api/v1/suites/{sid}/cases", json={"name": "c"}, headers=auth_headers)
    resp = await client.get(f"/api/v1/suites/{sid}/cases", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "c"


@pytest.mark.asyncio
async def test_manifest_and_dependency_endpoints(client, auth_headers):
    pc = await client.post(
        "/api/v1/projects", json={"name": "P", "prefix": "MANAPI"}, headers=auth_headers
    )
    pid = pc.json()["id"]
    sid = (
        await client.post(
            f"/api/v1/projects/{pid}/suites", json={"name": "S"}, headers=auth_headers
        )
    ).json()["id"]
    a = (
        await client.post(f"/api/v1/suites/{sid}/cases", json={"name": "a"}, headers=auth_headers)
    ).json()
    b = (
        await client.post(f"/api/v1/suites/{sid}/cases", json={"name": "b"}, headers=auth_headers)
    ).json()
    plan = (
        await client.post(
            f"/api/v1/projects/{pid}/plans", json={"name": "P1"}, headers=auth_headers
        )
    ).json()

    # add both cases to the plan
    await client.post(
        f"/api/v1/plans/{plan['id']}/cases",
        json={"case_ids": [a["id"], b["id"]], "urgency": 3},
        headers=auth_headers,
    )
    # b depends on a
    dep = await client.post(
        f"/api/v1/cases/{b['id']}/dependencies",
        json={"depends_on_case_id": a["id"]},
        headers=auth_headers,
    )
    assert dep.status_code == 201
    assert dep.json() == {"case_id": b["id"], "depends_on_case_id": a["id"]}

    # manifest reflects ordering + gating
    resp = await client.get(f"/api/v1/plans/{plan['id']}/manifest", headers=auth_headers)
    assert resp.status_code == 200
    manifest = {m["case_id"]: m for m in resp.json()}
    assert manifest[a["id"]]["order"] == 1 and manifest[a["id"]]["urgency"] == 3
    assert manifest[b["id"]]["blocked_by"] == [a["id"]]
    assert manifest[b["id"]]["runnable"] is False
