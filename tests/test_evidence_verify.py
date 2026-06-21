import pytest
from sqlalchemy import select

from app.models.user import User
from app.schemas.evidence import VerificationCreate
from app.schemas.execution import ExecutionCreate
from app.schemas.plan import PlanCreate
from app.schemas.project import ProjectCreate
from app.schemas.suite import SuiteCreate
from app.schemas.testcase import TestCaseCreate
from app.services import auth as auth_service
from app.services import evidence, executions, plans, projects, suites, testcases
from app.services.errors import Forbidden, NotFound


async def _execution_with_claim(session, prefix):
    p = await projects.create_project(session, ProjectCreate(name="P", prefix=prefix))
    s = await suites.create_suite(session, p.id, SuiteCreate(name="S"))
    tc = await testcases.create_test_case(session, s.id, TestCaseCreate(name="c"))
    plan = await plans.create_plan(session, p.id, PlanCreate(name="Plan"))
    ex = await executions.record_execution(
        session,
        ExecutionCreate(
            case_id=tc.id,
            plan_id=plan.id,
            build_name="b",
            status="pass",
            claims=["it works"],
        ),
        tester_id=None,
    )
    return ex


@pytest.mark.asyncio
async def test_unverified_then_verified(session, user):
    await _execution_with_claim(session, "VF1")
    unverified = await evidence.list_unverified_claims(session)
    assert len(unverified) == 1
    claim_id = unverified[0].id

    v = await evidence.verify_claim(
        session,
        claim_id,
        VerificationCreate(verdict="confirmed", reasoning={"why": "checked"}),
        auditor_id=user.id,
    )
    assert v.verdict == "confirmed"
    # claim no longer appears as unverified
    assert await evidence.list_unverified_claims(session) == []


@pytest.mark.asyncio
async def test_multiple_auditors_per_claim(session, user):
    await _execution_with_claim(session, "VF2")
    claim_id = (await evidence.list_unverified_claims(session))[0].id
    await evidence.verify_claim(
        session, claim_id, VerificationCreate(verdict="confirmed"), auditor_id=user.id
    )
    await evidence.verify_claim(
        session, claim_id, VerificationCreate(verdict="refuted"), auditor_id=user.id
    )
    verifications = await evidence.list_verifications(session, claim_id)
    assert {v.verdict for v in verifications} == {"confirmed", "refuted"}


@pytest.mark.asyncio
async def test_self_verification_rejected(session, user):
    # Doer != checker: the agent that filed a claim cannot verify it; a different
    # agent can. (user/'alice' is the auditor; 'bob' is the claimant.)
    claimant = User(
        login="bob",
        password_hash=auth_service.hash_password("pw"),
        email="bob@example.com",
        auth_method="agent",
        active=True,
    )
    session.add(claimant)
    await session.commit()
    await session.refresh(claimant)
    p = await projects.create_project(session, ProjectCreate(name="P", prefix="VF3"))
    s = await suites.create_suite(session, p.id, SuiteCreate(name="S"))
    tc = await testcases.create_test_case(session, s.id, TestCaseCreate(name="c"))
    plan = await plans.create_plan(session, p.id, PlanCreate(name="Plan"))
    await executions.record_execution(
        session,
        ExecutionCreate(
            case_id=tc.id, plan_id=plan.id, build_name="b", status="pass", claims=["it works"]
        ),
        tester_id=claimant.id,
    )
    claim_id = (await evidence.list_unverified_claims(session))[0].id

    with pytest.raises(Forbidden):
        await evidence.verify_claim(
            session, claim_id, VerificationCreate(verdict="confirmed"), auditor_id=claimant.id
        )
    # a different agent may verify
    v = await evidence.verify_claim(
        session, claim_id, VerificationCreate(verdict="confirmed"), auditor_id=user.id
    )
    assert v.verdict == "confirmed"


@pytest.mark.asyncio
async def test_verify_unknown_claim_raises(session, user):
    with pytest.raises(NotFound):
        await evidence.verify_claim(
            session, 999999, VerificationCreate(verdict="confirmed"), auditor_id=user.id
        )


@pytest.mark.asyncio
async def test_verify_endpoint(client, auth_headers, session, user):
    await _execution_with_claim(session, "VFE")
    unv = await client.get("/api/v1/claims/unverified", headers=auth_headers)
    assert unv.status_code == 200
    claim_id = unv.json()[0]["id"]
    resp = await client.post(
        f"/api/v1/claims/{claim_id}/verify",
        json={"verdict": "confirmed"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["verdict"] == "confirmed"


@pytest.mark.asyncio
async def test_list_unverified_claims_scoped_by_project(session):
    # Regression: project_id must actually filter (was accepted but ignored,
    # leaking claims across projects).
    ex_a = await _execution_with_claim(session, "VFA")
    await _execution_with_claim(session, "VFB")  # other project; must be excluded
    # resolve each execution's project via its version -> case
    from app.models.execution import Execution
    from app.models.testcase import TestCase, TestCaseVersion

    async def _project_of(ex_id):
        ex = await session.get(Execution, ex_id)
        ver = await session.get(TestCaseVersion, ex.version_id)
        case = await session.get(TestCase, ver.case_id)
        return case.project_id

    proj_a = await _project_of(ex_a.id)
    all_unverified = await evidence.list_unverified_claims(session)
    assert len(all_unverified) == 2
    scoped = await evidence.list_unverified_claims(session, project_id=proj_a)
    assert len(scoped) == 1
    assert scoped[0].execution_id == ex_a.id


@pytest.mark.asyncio
async def test_list_claims_with_latest_verdict_and_override(session, user):
    await _execution_with_claim(session, "LC1")
    claim_id = (await evidence.list_unverified_claims(session))[0].id

    # before verification: in list_claims with verdict=None
    rows = {r["id"]: r for r in await evidence.list_claims(session)}
    assert rows[claim_id]["verdict"] is None
    assert rows[claim_id]["verification_count"] == 0

    await evidence.verify_claim(
        session, claim_id, VerificationCreate(verdict="confirmed"), auditor_id=user.id
    )
    # override with a newer verdict
    await evidence.verify_claim(
        session, claim_id, VerificationCreate(verdict="refuted"), auditor_id=user.id
    )

    rows = {r["id"]: r for r in await evidence.list_claims(session)}
    assert rows[claim_id]["verdict"] == "refuted"  # latest wins
    assert rows[claim_id]["verification_count"] == 2  # history kept


@pytest.mark.asyncio
async def test_list_claims_scoped_by_project(session, user):
    await _execution_with_claim(session, "LC2A")
    ex_b = await _execution_with_claim(session, "LC2B")
    from app.models.testcase import TestCase, TestCaseVersion

    # project of ex_b
    pid = (
        await session.execute(
            select(TestCase.project_id)
            .join(TestCaseVersion, TestCaseVersion.case_id == TestCase.id)
            .where(TestCaseVersion.id == ex_b.version_id)
        )
    ).scalar_one()
    scoped = await evidence.list_claims(session, project_id=pid)
    assert len(scoped) == 1
