import pytest

from app.schemas.project import ProjectCreate
from app.schemas.requirement import ReqSpecCreate, RequirementCreate
from app.schemas.suite import SuiteCreate
from app.schemas.testcase import TestCaseCreate
from app.services import projects, requirements, suites, testcases


async def _setup(session, prefix):
    p = await projects.create_project(session, ProjectCreate(name="P", prefix=prefix))
    spec = await requirements.create_req_spec(
        session, p.id, ReqSpecCreate(doc_id="SRS", name="Spec")
    )
    s = await suites.create_suite(session, p.id, SuiteCreate(name="S"))
    tc = await testcases.create_test_case(session, s.id, TestCaseCreate(name="c"))
    return p, spec, tc


@pytest.mark.asyncio
async def test_create_requirement_with_coverage_links(session):
    p, spec, tc = await _setup(session, "CV1")
    await requirements.create_requirement(
        session,
        spec.id,
        RequirementCreate(req_doc_id="REQ-1", name="r", link_to_cases=[tc.id]),
    )
    trace = await requirements.get_traceability(session, p.id)
    assert len(trace) == 1
    assert trace[0].covered_case_ids == [tc.id]


@pytest.mark.asyncio
async def test_coverage_gaps(session):
    p, spec, tc = await _setup(session, "CV2")
    # one covered, one uncovered
    await requirements.create_requirement(
        session,
        spec.id,
        RequirementCreate(req_doc_id="REQ-1", name="covered", link_to_cases=[tc.id]),
    )
    await requirements.create_requirement(
        session, spec.id, RequirementCreate(req_doc_id="REQ-2", name="uncovered")
    )
    gaps = await requirements.get_coverage_gaps(session, p.id)
    assert len(gaps) == 1
    assert gaps[0].name == "uncovered"


@pytest.mark.asyncio
async def test_link_coverage_endpoint(client, auth_headers, session):
    p, spec, tc = await _setup(session, "CVE")
    req = await requirements.create_requirement(
        session, spec.id, RequirementCreate(req_doc_id="REQ-1", name="r")
    )
    # link via REST
    resp = await client.post(
        f"/api/v1/requirements/{req.id}/coverage",
        json={"case_ids": [tc.id]},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    trace = await client.get(f"/api/v1/projects/{p.id}/traceability", headers=auth_headers)
    assert trace.json()[0]["covered_case_ids"] == [tc.id]


@pytest.mark.asyncio
async def test_coverage_gaps_endpoint(client, auth_headers, session):
    p, spec, tc = await _setup(session, "CGE")
    await requirements.create_requirement(
        session, spec.id, RequirementCreate(req_doc_id="REQ-1", name="uncovered")
    )
    resp = await client.get(f"/api/v1/projects/{p.id}/coverage-gaps", headers=auth_headers)
    assert resp.status_code == 200
    assert any(g["name"] == "uncovered" for g in resp.json())
