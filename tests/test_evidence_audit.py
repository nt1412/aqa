import pytest

from app.schemas.evidence import AuditReportCreate
from app.schemas.execution import ExecutionCreate
from app.schemas.plan import PlanCreate
from app.schemas.project import ProjectCreate
from app.schemas.suite import SuiteCreate
from app.schemas.testcase import StepIn, TestCaseCreate
from app.services import evidence, executions, plans, projects, suites, testcases


async def _case(session, prefix):
    p = await projects.create_project(session, ProjectCreate(name="P", prefix=prefix))
    s = await suites.create_suite(session, p.id, SuiteCreate(name="S"))
    tc = await testcases.create_test_case(
        session, s.id, TestCaseCreate(name="c", steps=[StepIn(action="a")])
    )
    plan = await plans.create_plan(session, p.id, PlanCreate(name="Plan"))
    return tc, plan


@pytest.mark.asyncio
async def test_create_audit_report(session, user):
    tc, plan = await _case(session, "AU1")
    full = await testcases.get_test_case(session, tc.id)
    report = await evidence.create_audit_report(
        session,
        AuditReportCreate(
            entity_type="case_version",
            entity_id=full.current_version.id,
            findings={"issue": "shallow assertion"},
            quality_score=40,
        ),
        auditor_id=user.id,
    )
    assert report.id is not None
    assert report.quality_score == 40


@pytest.mark.asyncio
async def test_evaluate_test_case(session, user):
    tc, plan = await _case(session, "AU2")
    full = await testcases.get_test_case(session, tc.id)
    await executions.record_execution(
        session,
        ExecutionCreate(case_id=tc.id, plan_id=plan.id, build_name="b", status="pass"),
        tester_id=None,
    )
    ev = await evidence.evaluate_test_case(session, full.current_version.id)
    assert ev.step_count == 1
    assert ev.execution_count == 1
    assert ev.last_status == "pass"


@pytest.mark.asyncio
async def test_audit_report_endpoint(client, auth_headers, session, user):
    tc, plan = await _case(session, "AUE")
    full = await testcases.get_test_case(session, tc.id)
    resp = await client.post(
        "/api/v1/audit-reports",
        json={
            "entity_type": "case_version",
            "entity_id": full.current_version.id,
            "quality_score": 80,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["quality_score"] == 80
