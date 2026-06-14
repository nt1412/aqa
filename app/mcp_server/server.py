"""AgentQA MCP server.

Tools wrap the service layer directly. Each tool opens its own DB session.
Phase 1 implements the 6 entity-backed tools; the rest are registered as
explicit stubs raising NotImplementedError until their phase lands.
"""

import base64
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from app.db import SessionLocal
from app.schemas.execution import ExecutionCreate, StepResultIn
from app.schemas.testcase import StepIn, TestCaseCreate
from app.services import assignments, evidence, executions, requirements, suites, testcases

mcp = FastMCP("agentqa")


@asynccontextmanager
async def _session():
    async with SessionLocal() as s:
        yield s


def _version_dump(out) -> dict | None:
    if out.current_version is None:
        return None
    cv = out.current_version
    return {
        "version": cv.version,
        "summary": cv.summary,
        "preconditions": cv.preconditions,
        "importance": cv.importance,
        "execution_type": cv.execution_type,
        "status": cv.status,
        "steps": [
            {
                "step_number": s.step_number,
                "action": s.action,
                "expected_result": s.expected_result,
            }
            for s in cv.steps
        ],
    }


def _case_dump(out) -> dict:
    return {
        "id": out.id,
        "external_id": out.external_id,
        "name": out.name,
        "suite_id": out.suite_id,
        "project_id": out.project_id,
        "current_version": _version_dump(out),
    }


# ---------- Phase 1: entity-backed tools ----------


@mcp.tool()
async def create_test_suite(project_id: int, path: str, details: str | None = None) -> dict:
    """Find-or-create a test suite by slash-delimited path, e.g. 'Auth/Login/OAuth'."""
    async with _session() as s:
        suite = await suites.find_or_create_path(s, project_id, path)
        return {"id": suite.id, "name": suite.name, "parent_id": suite.parent_id}


@mcp.tool()
async def create_test_case(
    project_id: int,
    suite_path: str,
    name: str,
    summary: str | None = None,
    preconditions: str | None = None,
    steps: list[dict] | None = None,
    importance: int = 2,
    execution_type: str = "manual",
) -> dict:
    """Create a full test case (with version 1 + steps) under a suite path."""
    async with _session() as s:
        suite = await suites.find_or_create_path(s, project_id, suite_path)
        tc = await testcases.create_test_case(
            s,
            suite.id,
            TestCaseCreate(
                name=name,
                summary=summary,
                preconditions=preconditions,
                importance=importance,
                execution_type=execution_type,
                steps=[StepIn(**st) for st in (steps or [])],
            ),
        )
        out = await testcases.get_test_case(s, tc.id)
        return _case_dump(out)


@mcp.tool()
async def bulk_create_test_cases(project_id: int, suite_path: str, cases: list[dict]) -> list[dict]:
    """Create many test cases under one suite path in a single call."""
    async with _session() as s:
        suite = await suites.find_or_create_path(s, project_id, suite_path)
        created = []
        for c in cases:
            tc = await testcases.create_test_case(
                s,
                suite.id,
                TestCaseCreate(
                    name=c["name"],
                    summary=c.get("summary"),
                    preconditions=c.get("preconditions"),
                    importance=c.get("importance", 2),
                    execution_type=c.get("execution_type", "manual"),
                    steps=[StepIn(**st) for st in c.get("steps", [])],
                ),
            )
            out = await testcases.get_test_case(s, tc.id)
            created.append(_case_dump(out))
        return created


@mcp.tool()
async def get_test_case(
    case_id: int | None = None,
    external_id: str | None = None,
    project_id: int | None = None,
) -> dict:
    """Fetch a test case (current version + steps) by id, or external_id + project_id."""
    async with _session() as s:
        if case_id is not None:
            out = await testcases.get_test_case(s, case_id)
        elif external_id is not None and project_id is not None:
            out = await testcases.get_by_external_id(s, project_id, external_id)
        else:
            raise ValueError("provide case_id, or external_id + project_id")
        return _case_dump(out)


@mcp.tool()
async def search_test_cases(project_id: int, query: str) -> list[dict]:
    """Search test cases by name substring — call before creating duplicates."""
    async with _session() as s:
        rows = await testcases.search_test_cases(s, project_id, query)
        return [{"id": r.id, "external_id": r.external_id, "name": r.name} for r in rows]


@mcp.tool()
async def record_test_run(
    case_id: int,
    plan_id: int,
    build_name: str,
    status: str,
    commit_id: str | None = None,
    step_results: list[dict] | None = None,
    notes: str | None = None,
    session_id: str | None = None,
    claims: list[str] | None = None,
    reasoning: dict | None = None,
    agent_id: int | None = None,
    agent_model: str | None = None,
) -> dict:
    """Record an execution result. Build is upserted by (plan, build_name).

    Optionally attach claims (assertions the agent is proving) and a reasoning
    blob (its chain-of-thought), persisted as evidence for later verification.
    Pass agent_id (the recording agent's user id) so the run shows up in
    get_agent_execution_history, and agent_model to capture provenance.
    """
    async with _session() as s:
        ex = await executions.record_execution(
            s,
            ExecutionCreate(
                case_id=case_id,
                plan_id=plan_id,
                build_name=build_name,
                commit_id=commit_id,
                status=status,
                step_results=[StepResultIn(**sr) for sr in (step_results or [])],
                notes=notes,
                session_id=session_id,
                claims=claims or [],
                reasoning=reasoning,
                agent_model=agent_model,
            ),
            tester_id=agent_id,  # the recording agent's user id (None if anonymous)
        )
        return {
            "id": ex.id,
            "status": ex.status,
            "build_id": ex.build_id,
            "version_id": ex.version_id,
        }


@mcp.tool()
async def assign_test(
    case_id: int,
    plan_id: int,
    assignee_id: int,
    assignee_type: str,
    deadline: str | None = None,
) -> dict:
    """Assign a test case (in a plan) to a human or agent. assignee_type: human|agent."""
    import datetime as _dt

    parsed_deadline = _dt.datetime.fromisoformat(deadline) if deadline else None
    async with _session() as s:
        from app.schemas.assignment import AssignmentCreate

        a = await assignments.create_assignment(
            s,
            AssignmentCreate(
                case_id=case_id,
                plan_id=plan_id,
                assignee_id=assignee_id,
                assignee_type=assignee_type,
                deadline=parsed_deadline,
            ),
            assigner_id=None,  # MCP callers are agents; no human assigner
        )
        return {"id": a.id, "status": a.status, "assignee_id": a.assignee_id}


@mcp.tool()
async def list_assignments(
    plan_id: int | None = None,
    assignee_id: int | None = None,
    status: str | None = None,
) -> list[dict]:
    """List assignments, optionally filtered — agents poll this to discover work."""
    async with _session() as s:
        rows = await assignments.list_assignments(s, plan_id, assignee_id, status)
        return [
            {
                "id": a.id,
                "case_id": a.case_id,
                "plan_id": a.plan_id,
                "assignee_id": a.assignee_id,
                "assignee_type": a.assignee_type,
                "status": a.status,
            }
            for a in rows
        ]


# ---------- Phase 2b: evidence & provenance tools ----------


@mcp.tool()
async def upload_artifact(
    execution_id: int,
    artifact_type: str,
    title: str,
    content_base64: str,
    mime_type: str | None = None,
) -> dict:
    """Upload a base64-encoded artifact (trace/log/screenshot/dump) for an execution."""
    async with _session() as s:
        art = await evidence.upload_artifact(
            s,
            execution_id,
            artifact_type,
            title,
            base64.b64decode(content_base64),
            mime_type,
        )
        return {"id": art.id, "artifact_type": art.artifact_type, "blob_key": art.blob_key}


@mcp.tool()
async def list_unverified_claims(
    project_id: int | None = None, plan_id: int | None = None
) -> list[dict]:
    """Claims awaiting verification — audit agents poll this."""
    async with _session() as s:
        rows = await evidence.list_unverified_claims(s, project_id, plan_id)
        return [
            {"id": c.id, "execution_id": c.execution_id, "claim_text": c.claim_text} for c in rows
        ]


@mcp.tool()
async def verify_claim(
    claim_id: int, verdict: str, auditor_id: int, reasoning: dict | None = None
) -> dict:
    """Submit a verdict (confirmed|refuted|inconclusive) for a claim."""
    from app.schemas.evidence import VerificationCreate

    async with _session() as s:
        v = await evidence.verify_claim(
            s,
            claim_id,
            VerificationCreate(verdict=verdict, reasoning=reasoning),
            auditor_id=auditor_id,
        )
        return {"id": v.id, "claim_id": v.claim_id, "verdict": v.verdict}


@mcp.tool()
async def create_audit_report(
    entity_type: str,
    entity_id: int,
    auditor_id: int,
    findings: dict | None = None,
    quality_score: int | None = None,
) -> dict:
    """File an audit report against a case_version|suite|plan."""
    from app.schemas.evidence import AuditReportCreate

    async with _session() as s:
        r = await evidence.create_audit_report(
            s,
            AuditReportCreate(
                entity_type=entity_type,
                entity_id=entity_id,
                findings=findings,
                quality_score=quality_score,
            ),
            auditor_id=auditor_id,
        )
        return {"id": r.id, "entity_type": r.entity_type, "quality_score": r.quality_score}


@mcp.tool()
async def evaluate_test_case(case_version_id: int) -> dict:
    """Return a test case version's shape + execution stats for quality assessment."""
    async with _session() as s:
        ev = await evidence.evaluate_test_case(s, case_version_id)
        return ev.model_dump()


@mcp.tool()
async def get_execution_evidence(case_id: int) -> dict:
    """Full evidence bundle for a case: executions with claims + artifacts."""
    async with _session() as s:
        bundle = await evidence.get_execution_evidence(s, case_id)
        return bundle.model_dump(mode="json")


@mcp.tool()
async def get_agent_execution_history(agent_id: int, project_id: int | None = None) -> list[dict]:
    """All executions recorded by a given agent — supervision/pattern analysis."""
    async with _session() as s:
        rows = await evidence.get_agent_execution_history(s, agent_id, project_id)
        return [
            {
                "id": e.id,
                "version_id": e.version_id,
                "status": e.status,
                "plan_id": e.plan_id,
                "build_id": e.build_id,
            }
            for e in rows
        ]


@mcp.tool()
async def get_failure_context(case_id: int, plan_id: int | None = None, last_n: int = 5) -> dict:
    """Self-correction bundle: a case's recent failures, step failures, reasoning,
    artifacts, and semantically similar failures elsewhere."""
    async with _session() as s:
        ctx = await evidence.get_failure_context(s, case_id, plan_id, last_n)
        return ctx.model_dump(mode="json")


@mcp.tool()
async def search_similar_failures(case_id: int, n: int = 5) -> list[dict]:
    """Find failures across other cases whose reasoning is semantically closest."""
    async with _session() as s:
        rows = await evidence.search_similar_failures(s, case_id, n)
        return [r.model_dump() for r in rows]


# ---------- Phase 2d: requirements & coverage tools ----------


@mcp.tool()
async def create_requirement(
    spec_id: int,
    req_doc_id: str,
    name: str,
    scope: str | None = None,
    link_to_cases: list[int] | None = None,
) -> dict:
    """Create a requirement (+v1) under a spec, optionally linking it to test cases."""
    from app.schemas.requirement import RequirementCreate

    async with _session() as s:
        out = await requirements.create_requirement(
            s,
            spec_id,
            RequirementCreate(
                req_doc_id=req_doc_id,
                name=name,
                scope=scope,
                link_to_cases=link_to_cases or [],
            ),
        )
        return {"id": out.id, "req_doc_id": out.req_doc_id, "name": out.name}


@mcp.tool()
async def get_coverage_gaps(project_id: int, spec_id: int | None = None) -> list[dict]:
    """Requirements with no active test coverage — gap analysis."""
    async with _session() as s:
        gaps = await requirements.get_coverage_gaps(s, project_id, spec_id)
        return [g.model_dump() for g in gaps]


# ---------- Deferred tools (registered, bodies land in later phases) ----------

_DEFERRED = []


def _make_stub(tool_name: str):
    @mcp.tool(name=tool_name)
    async def _stub(**kwargs) -> dict:
        raise NotImplementedError(f"{tool_name} is implemented in a later phase")

    return _stub


for _name in _DEFERRED:
    _make_stub(_name)


def main():
    """Launch the MCP server.

    Transport is chosen via AGENTQA_MCP_TRANSPORT (default 'stdio' — the client
    spawns this process). Set it to 'streamable-http' (or 'sse') to run a
    long-lived networked server other agents connect to over a URL; host/port
    come from AGENTQA_MCP_HOST / AGENTQA_MCP_PORT (default 127.0.0.1:8001).
    """
    import os

    transport = os.environ.get("AGENTQA_MCP_TRANSPORT", "stdio")
    if transport != "stdio":
        mcp.settings.host = os.environ.get("AGENTQA_MCP_HOST", "127.0.0.1")
        mcp.settings.port = int(os.environ.get("AGENTQA_MCP_PORT", "8001"))
        mcp.run(transport=transport)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
