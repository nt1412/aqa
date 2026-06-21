"""Phase 3: keyword/FTS recurrence retrieval with a natural silence gate.

The acceptance gate (the reason this exists): a query with no genuine prior in
the corpus must return NOTHING. Cosine had no usable threshold for that; keyword
FTS does — no shared lexemes -> no match -> silence.
"""

import pytest

from app.schemas.execution import ExecutionCreate
from app.schemas.plan import PlanCreate
from app.schemas.project import ProjectCreate
from app.schemas.suite import SuiteCreate
from app.schemas.testcase import TestCaseCreate
from app.services import evidence, executions, plans, projects, suites, testcases


async def _case_with_reasoning(session, pid, plan_id, name, root_cause):
    s = await suites.create_suite(session, pid, SuiteCreate(name=f"S-{name}"))
    tc = await testcases.create_test_case(session, s.id, TestCaseCreate(name=name))
    await executions.record_execution(
        session,
        ExecutionCreate(
            case_id=tc.id, plan_id=plan_id, build_name="b", status="fail",
            reasoning={"root_cause": root_cause},
        ),
        tester_id=None,
    )
    return tc


@pytest.fixture
async def _corpus(session):
    p = await projects.create_project(session, ProjectCreate(name="P", prefix="REC1"))
    plan = await plans.create_plan(session, p.id, PlanCreate(name="Plan"))
    alias = await _case_with_reasoning(
        session, p.id, plan.id, "alias-gap",
        "Lambda :prod alias points to an old version predating the ENA fix; promote the alias",
    )
    await _case_with_reasoning(
        session, p.id, plan.id, "money",
        "integer truncation drops fractional cents in the order total",
    )
    await _case_with_reasoning(
        session, p.id, plan.id, "vnc",
        "noVNC reconnect storm; shared websockify self-DoS",
    )
    return p, alias


@pytest.mark.asyncio
async def test_recurrence_recall_surfaces_the_prior(session, _corpus):
    p, alias = _corpus
    hits = await evidence.search_recurrences(
        session, "the prod alias is stale and points to an old lambda version", project_id=p.id
    )
    assert hits, "a genuine prior should be retrieved"
    assert hits[0].case_id == alias.id


@pytest.mark.asyncio
async def test_recurrence_silence_on_no_prior(session, _corpus):
    # SILENCE GATE: a failure with no genuine prior shares no lexemes -> nothing.
    p, _ = _corpus
    hits = await evidence.search_recurrences(
        session, "kubernetes pod CrashLoopBackOff on the readiness probe", project_id=p.id
    )
    assert hits == []


@pytest.mark.asyncio
async def test_recurrence_silence_on_single_common_term(session, _corpus):
    # one shared common word ("promote") with an otherwise-unrelated failure is
    # NOT a recurrence — the >=2-distinct-terms gate must keep it silent.
    p, _ = _corpus
    hits = await evidence.search_recurrences(
        session, "promote the staging database to a new server", project_id=p.id
    )
    assert hits == []


@pytest.mark.asyncio
async def test_recurrence_empty_query_is_silent(session, _corpus):
    p, _ = _corpus
    assert await evidence.search_recurrences(session, "", project_id=p.id) == []
    assert await evidence.search_recurrences(session, "   ", project_id=p.id) == []
