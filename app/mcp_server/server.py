"""AQA MCP server — workflow tools wrapping the shared service layer.

Each tool opens its own DB session via _session(). Per-agent auth is opt-in
(AQA_MCP_REQUIRE_AUTH): when on, every tool except register_agent requires a
valid X-API-Key and the authenticated identity drives attribution. See
docs/agent-guide.md for the agent workflow.
"""

import base64
import datetime as _dt
import os
from contextlib import asynccontextmanager
from contextvars import ContextVar

from mcp.server.fastmcp import FastMCP
from mcp.server.lowlevel.server import request_ctx

from app.db import SessionLocal
from app.schemas.execution import ExecutionCreate, StepResultIn
from app.schemas.testcase import StepIn, TestCaseCreate
from app.services import (
    annotations,
    assignments,
    evidence,
    executions,
    lineage,
    plans,
    projects,
    requirements,
    reruns,
    suites,
    testcases,
    users,
)
from app.services import (
    auth as auth_service,
)
from app.services.errors import Unauthorized

mcp = FastMCP("aqa")

# ---------- lightweight per-agent auth (opt-in via AQA_MCP_REQUIRE_AUTH) ----------
# When enabled, every tool except register_agent requires a valid X-API-Key header
# (an agent's own key, from register_agent). The authenticated identity also
# overrides any caller-supplied agent_id/auditor_id, so attribution can't be spoofed.

# the authenticated agent for the current request (set by _session)
_auth_agent: ContextVar = ContextVar("aqa_mcp_agent", default=None)


class AuthRequired(Exception):
    """MCP auth is enabled but the request carried no valid API key."""


def _env(key: str, default=None):
    """Read AQA_* env, falling back to the legacy AGENTQA_* name (rename compat)."""
    v = os.environ.get(key)
    if v is None:
        v = os.environ.get(key.replace("AQA_", "AGENTQA_", 1))
    return v if v is not None else default


def _auth_enabled() -> bool:
    return _env("AQA_MCP_REQUIRE_AUTH", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _request_headers():
    """Headers on the current MCP request, or None outside a request."""
    try:
        req = request_ctx.get().request
    except LookupError:
        return None
    return getattr(req, "headers", None)


def _request_api_key() -> str | None:
    """The X-API-Key (or Bearer token) on the current MCP request, if any."""
    headers = _request_headers()
    if headers is None:
        return None
    key = headers.get("x-api-key")
    if not key:
        authz = headers.get("authorization") or ""
        if authz.lower().startswith("bearer "):
            key = authz.split(" ", 1)[1].strip()
    return key or None


def _request_enroll_key() -> str | None:
    """The X-Enroll-Key on the current MCP request, if any."""
    headers = _request_headers()
    return headers.get("x-enroll-key") if headers is not None else None


async def _current_agent(session):
    key = _request_api_key()
    if not key:
        return None
    try:
        return await auth_service.user_from_api_key(session, key)
    except Unauthorized:
        return None


async def _require_agent(session):
    """Enforce auth when enabled. Returns the authenticated user, or None when
    auth is disabled. Raises AuthRequired when enabled and no valid key."""
    if not _auth_enabled():
        return None
    agent = await _current_agent(session)
    if agent is None:
        raise AuthRequired(
            "MCP auth is enabled — pass a valid X-API-Key header "
            "(an agent key from register_agent / `aqa agent register`)."
        )
    return agent


def _json_safe(obj):
    """Recursively make a value JSON-serializable for an MCP tool return — chiefly
    datetimes → ISO strings. REST serializes these automatically; MCP does not, so
    tools wrap service dicts in this rather than each service remembering to."""
    if isinstance(obj, _dt.datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _provenance_id(passed_id):
    """The authenticated agent's id overrides a caller-supplied id so attribution
    can't be spoofed; falls back to the passed id when auth is disabled."""
    agent = _auth_agent.get()
    return agent.id if agent is not None else passed_id


def _check_enrollment() -> None:
    """Gate registration when auth is enabled. register_agent must stay reachable
    without a per-agent key (it mints one), but open registration would defeat
    auth — anyone could mint a key and authenticate. So require a shared
    enrollment secret (X-Enroll-Key == AQA_MCP_ENROLL_KEY). Fails closed:
    if auth is on and no enroll key is configured, registration is refused."""
    if not _auth_enabled():
        return
    expected = _env("AQA_MCP_ENROLL_KEY")
    if not expected or _request_enroll_key() != expected:
        raise AuthRequired(
            "MCP auth is enabled — registration requires a valid X-Enroll-Key "
            "header (the operator's enrollment secret)."
        )


@asynccontextmanager
async def _session(require_auth: bool = True):
    async with SessionLocal() as s:
        agent = await _require_agent(s) if require_auth else None
        token = _auth_agent.set(agent)
        try:
            yield s
        finally:
            _auth_agent.reset(token)


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


# ---------- Public discovery (no auth) ----------


@mcp.tool()
async def get_orientation() -> dict:
    """Public landing page (no auth, no enrollment): what AQA is and how an
    agent uses it. Read this to decide whether to join; register_agent then mints
    your identity + key. Returns no secrets — just workflow docs."""
    from app.agent_orientation import AGENT_ORIENTATION

    return {"orientation": AGENT_ORIENTATION}


# ---------- Phase 1: entity-backed tools ----------


@mcp.tool()
async def create_project(name: str, prefix: str) -> dict:
    """Onboard a new project — the top-level container for suites/cases/plans.

    The prefix is permanent, unique, and drives external IDs (e.g. 'MSVC-1').
    Returns the project id to use with the other tools.
    """
    from app.schemas.project import ProjectCreate

    async with _session() as s:
        p = await projects.create_project(s, ProjectCreate(name=name, prefix=prefix))
        return {"id": p.id, "name": p.name, "prefix": p.prefix}


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
    branch: str | None = None,
    base_commit: str | None = None,
    step_results: list[dict] | None = None,
    notes: str | None = None,
    session_id: str | None = None,
    claims: list[str] | None = None,
    reasoning: dict | None = None,
    agent_id: int | None = None,
    agent_model: str | None = None,
    cascade_blocked: bool = True,
) -> dict:
    """Record an execution result. Build is upserted by (plan, build_name).

    Optionally attach claims (assertions the agent is proving) and a reasoning
    blob (its chain-of-thought), persisted as evidence for later verification.
    Pass agent_id (the recording agent's user id) so the run shows up in
    get_agent_execution_history, and agent_model to capture provenance.

    For branch-aware lineage, pass branch (the branch this build ran on) and
    base_commit (git merge-base HEAD <default-branch>) so the branch's delta vs
    main resolves precisely. Both are backfilled once per (plan, build_name).

    When status is fail/blocked and cascade_blocked is true (default), cases
    downstream of this one (via add_test_dependency) that are in the same plan
    are auto-recorded 'blocked' for this build — so the run reflects what can't
    be trusted. Cases already recorded for the build are left untouched.
    """
    async with _session() as s:
        ex = await executions.record_execution(
            s,
            ExecutionCreate(
                case_id=case_id,
                plan_id=plan_id,
                build_name=build_name,
                commit_id=commit_id,
                branch=branch,
                base_commit=base_commit,
                status=status,
                step_results=[StepResultIn(**sr) for sr in (step_results or [])],
                notes=notes,
                session_id=session_id,
                claims=claims or [],
                reasoning=reasoning,
                agent_model=agent_model,
            ),
            # authenticated identity overrides a passed agent_id (anti-spoof);
            # falls back to agent_id when MCP auth is disabled
            tester_id=_provenance_id(agent_id),
            cascade=cascade_blocked,
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
            auditor_id=_provenance_id(auditor_id),  # authenticated identity wins
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
            auditor_id=_provenance_id(auditor_id),  # authenticated identity wins
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
    the last passing run's reasoning (why it was last green — often the fix for a
    recurrence), artifacts, and semantically similar failures elsewhere."""
    async with _session() as s:
        ctx = await evidence.get_failure_context(s, case_id, plan_id, last_n)
        return ctx.model_dump(mode="json")


@mcp.tool()
async def search_similar_failures(case_id: int, n: int = 5) -> list[dict]:
    """Find failures across other cases whose reasoning is semantically closest."""
    async with _session() as s:
        rows = await evidence.search_similar_failures(s, case_id, n)
        return [r.model_dump() for r in rows]


@mcp.tool()
async def search_recurrences(
    query_text: str, project_id: int | None = None, n: int = 5
) -> list[dict]:
    """Keyword search over prior failure/fix reasoning for recurrences of a pattern.

    Pass the current failure's symptom or root-cause text. Returns BOTH passing and
    failing prior runs (a fix is often documented in a pass). Empty result means no
    prior shares vocabulary — i.e. 'no known prior' (a real signal, not an error)."""
    async with _session() as s:
        hits = await evidence.search_recurrences(s, query_text, project_id, n)
        return [h.model_dump() for h in hits]


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
async def link_coverage(req_id: int, case_ids: list[int]) -> dict:
    """Link a requirement to test cases as coverage, after the requirement exists.

    Use this to attach tests to a requirement you registered earlier (the
    register-now, cover-as-tests-land loop). Idempotent — re-linking a case is a
    no-op. Closes the requirement's entry in get_coverage_gaps.
    """
    async with _session() as s:
        links = await requirements.link_requirement_coverage(s, req_id, case_ids)
        return {"req_id": req_id, "linked_case_ids": case_ids, "coverage_count": len(links)}


@mcp.tool()
async def get_coverage_gaps(project_id: int, spec_id: int | None = None) -> list[dict]:
    """Requirements with no active test coverage — gap analysis."""
    async with _session() as s:
        gaps = await requirements.get_coverage_gaps(s, project_id, spec_id)
        return [g.model_dump() for g in gaps]


# ---------- lineage: build/commit/run history ----------


@mcp.tool()
async def list_build_timeline(plan_id: int) -> list[dict]:
    """Builds for a plan, newest first, each with commit/branch and a
    pass/fail/blocked/not_run rollup + pass_rate. The build timeline."""
    async with _session() as s:
        return _json_safe(await lineage.list_builds_enriched(s, plan_id))


@mcp.tool()
async def get_build_detail(build_id: int) -> dict:
    """A build's header (commit, branch, base_commit), its rollup, and each
    case's latest result in that build (collapsing re-runs to the latest)."""
    async with _session() as s:
        return _json_safe(await lineage.build_detail(s, build_id))


@mcp.tool()
async def get_case_history(case_id: int) -> dict:
    """A case's latest result per build, chronological (build, branch, commit,
    status), plus derived broke/fixed transitions — the known regression path."""
    async with _session() as s:
        return _json_safe(await lineage.case_history(s, case_id))


@mcp.tool()
async def compare_builds(build_id: int, to: str = "baseline") -> dict:
    """Classify each case between a build and another build (to=<id>) or its
    auto-resolved default-branch baseline (to='baseline'): regression / fixed /
    still_failing / still_passing / new_test / removed. A regression (was green
    on baseline, now red) is never conflated with a new_test (no baseline)."""
    async with _session() as s:
        return _json_safe(await lineage.compare(s, build_id, to))


@mcp.tool()
async def list_branch_status(project_id: int) -> list[dict]:
    """Merge-readiness per active branch. The verdict is summed across ALL plans
    that ran at the branch's head commit — BLOCKED if any plan regressed vs its
    baseline, else READY — so a green plan can't mask a regressing one. Includes
    per-plan breakdown. This is the pre-merge gate a human and agent share."""
    async with _session() as s:
        return _json_safe(await lineage.branch_status(s, project_id))


@mcp.tool()
async def get_case_status_map(project_id: int) -> dict:
    """Per-case latest run-status + recent statuses across the project — the
    'is this case green right now?' map the suite browser renders inline."""
    async with _session() as s:
        smap = await lineage.case_status_map(s, project_id)
        # JSON object keys must be strings
        return {str(cid): v for cid, v in smap.items()}


@mcp.tool()
async def get_project_health(project_id: int) -> dict:
    """Project health: latest build per plan + rollup, pass-rate trend, flaky
    candidates (cases that flip status repeatedly), open regression count, and
    re-investigations avoidable (open regressions with a cached fix-path)."""
    async with _session() as s:
        return _json_safe(await lineage.project_health(s, project_id))


@mcp.tool()
async def get_known_regressions(
    project_id: int, branch: str | None = None, case_ids: list[int] | None = None
) -> list[dict]:
    """Call this BEFORE investigating a failure. Returns open regressions on active
    branches, each annotated with its known fix-path (the commit that broke it, the
    commit that fixed it last time, and the prior reasoning) when one exists. A hit
    means an expensive re-investigation can be skipped — the answer is cached.
    Each cached fix served here is logged as a re-investigation avoided (feeds the
    health 'reinvestigations_avoided' metric)."""
    async with _session() as s:
        regs = await lineage.known_regressions(s, project_id, branch, case_ids)
        await lineage.record_guard_hits(s, project_id, regs)
        return _json_safe(regs)


@mcp.tool()
async def create_annotation(
    entity_type: str, entity_id: int, text: str, author_id: int | None = None
) -> dict:
    """Attach a note to an entity (entity_type e.g. 'regression'|'case'|'build',
    entity_id its id) — the human+agent collaboration trail. Author defaults to
    the authenticated identity."""
    async with _session() as s:
        a = await annotations.create_annotation(
            s, entity_type, entity_id, text, _provenance_id(author_id)
        )
        return {"id": a.id, "entity_type": a.entity_type, "entity_id": a.entity_id}


@mcp.tool()
async def list_annotations(entity_type: str, entity_id: int) -> list[dict]:
    """Notes attached to an entity, oldest first."""
    async with _session() as s:
        rows = await annotations.list_annotations(s, entity_type, entity_id)
        return [
            {"id": a.id, "author_id": a.author_id, "text": a.text} for a in rows
        ]


@mcp.tool()
async def set_quarantine(case_id: int, quarantined: bool = True) -> dict:
    """Quarantine (or un-quarantine) a known-flaky case. Quarantined cases still
    run and record, but are excluded from the merge-readiness verdict and the
    known-regression guard, so flaky noise can't block a merge or bury real
    regressions."""
    async with _session() as s:
        tc = await testcases.set_quarantine(s, case_id, quarantined)
        return {"id": tc.id, "external_id": tc.external_id, "quarantined": tc.quarantined}


@mcp.tool()
async def request_rerun(
    build_id: int,
    assignee_id: int,
    case_id: int | None = None,
    assigner_id: int | None = None,
    assignee_type: str = "agent",
) -> list[dict]:
    """Request a re-run of a case (case_id given) or the whole build (omit case_id),
    as 'rerun' assignments the assignee discovers via list_assignments — the shared
    human+agent work queue. Idempotent: no duplicate open rerun for a (case, build)."""
    async with _session() as s:
        created = await reruns.request_rerun(
            s,
            build_id=build_id,
            assignee_id=assignee_id,
            assigner_id=_provenance_id(assigner_id),
            case_id=case_id,
            assignee_type=assignee_type,
        )
        return [
            {"id": a.id, "case_id": a.case_id, "build_id": a.build_id, "status": a.status}
            for a in created
        ]


@mcp.tool()
async def register_agent(
    login: str,
    agent_model: str | None = None,
    email: str | None = None,
    display_name: str | None = None,
) -> dict:
    """Register an agent identity so your work is attributable.

    Creates a user with auth_method='agent' and returns its id, a one-time API
    key, AND an orientation that tells you how to use the platform — read it.
    Call this once at the start of a session, then pass the returned id as
    agent_id to record_test_run (and as auditor_id to verify_claim /
    create_audit_report) so your runs show up in get_agent_execution_history.
    The api_key is returned ONCE — save it to authenticate to the REST API;
    only its hash is stored. Pick a unique login (re-using one raises an error).
    """
    from app.agent_orientation import AGENT_ORIENTATION

    # Bootstrap, but gated: when auth is enabled, require the enrollment secret —
    # otherwise open registration would mint a valid key to anyone and defeat auth.
    _check_enrollment()
    async with _session(require_auth=False) as s:
        user, api_key = await users.register_agent(
            s,
            login=login,
            agent_model=agent_model,
            email=email,
            display_name=display_name,
        )
        return {
            "id": user.id,
            "login": user.login,
            "agent_model": user.agent_model,
            "auth_method": user.auth_method,
            "api_key": api_key,
            "orientation": AGENT_ORIENTATION,
        }


# ---------- Test hierarchy & ordering (agent-facing run planning) ----------


def _suite_node_dump(node, counts: dict) -> dict:
    return {
        "id": node.id,
        "name": node.name,
        "parent_id": node.parent_id,
        "case_count": counts.get(node.id, 0),
        "children": [_suite_node_dump(c, counts) for c in node.children],
    }


@mcp.tool()
async def get_suite_tree(project_id: int) -> list[dict]:
    """The suite hierarchy for a project as a nested tree with per-suite case counts.

    Use this to discover how tests are organized and to run a whole branch
    (e.g. everything under 'Purple'). Each node: id, name, parent_id,
    case_count, children[]. Pair with get_test_case / search_test_cases to
    pull the cases in a chosen suite.
    """
    async with _session() as s:
        tree = await suites.get_tree(s, project_id)
        counts = await suites.case_counts(s, project_id)
        return [_suite_node_dump(n, counts) for n in tree]


@mcp.tool()
async def list_agents() -> list[dict]:
    """List agent identities (id, login, agent_model, active) — find probe/stale
    ones to clean up."""
    async with _session() as s:
        return [
            {"id": u.id, "login": u.login, "agent_model": u.agent_model, "active": u.active}
            for u in await users.list_agents(s)
        ]


@mcp.tool()
async def deactivate_agent(user_id: int) -> dict:
    """Soft-delete an agent identity (mark inactive) so it can no longer
    authenticate and drops from active lists. Recorded work stays attributable.
    Use to clean up verification/probe registrations."""
    async with _session() as s:
        u = await users.deactivate_user(s, user_id)
        return {"id": u.id, "login": u.login, "active": u.active}


@mcp.tool()
async def create_test_plan(project_id: int, name: str, notes: str | None = None) -> dict:
    """Create a test plan — the container an agent fills with an ordered run list.

    Returns its id; pass that to add_cases_to_plan and get_run_manifest.
    """
    from app.schemas.plan import PlanCreate

    async with _session() as s:
        plan = await plans.create_plan(s, project_id, PlanCreate(name=name, notes=notes))
        return {"id": plan.id, "name": plan.name, "project_id": plan.project_id}


@mcp.tool()
async def add_cases_to_plan(
    plan_id: int, case_ids: list[int], urgency: int = 2
) -> list[dict]:
    """Add test cases to a plan's run list (appended in order), pinning their
    current versions. Build the prioritized manifest agents execute. urgency
    1=low, 2=medium, 3=high. Idempotent per (plan, case version).
    """
    async with _session() as s:
        links = await plans.add_cases(s, plan_id, case_ids, urgency=urgency)
        return [
            {"id": link.id, "version_id": link.version_id, "order": link.order}
            for link in links
        ]


@mcp.tool()
async def add_test_dependency(case_id: int, depends_on_case_id: int) -> dict:
    """Record that one test case depends on another (a prerequisite that must
    pass first). Used for execution gating: get_run_manifest marks a case
    blocked_by any prerequisite not yet passing. Rejects self-deps,
    cross-project deps, and cycles.
    """
    async with _session() as s:
        rel = await testcases.add_dependency(s, case_id, depends_on_case_id)
        return {
            "case_id": rel.source_id,
            "depends_on_case_id": rel.dest_id,
            "relation_type": rel.relation_type,
        }


@mcp.tool()
async def get_run_manifest(plan_id: int, build_id: int | None = None) -> list[dict]:
    """The ordered, priority- and dependency-aware run list for a plan.

    This is what a QA agent fetches to know WHAT to run and IN WHAT ORDER.
    Each entry: order, urgency, case_id, external_id, name, importance,
    latest_status, depends_on, blocked_by, runnable. Run entries top-down;
    skip any with runnable=false (record them blocked, citing blocked_by).

    Pass build_id to gate against that build only (regression: a prerequisite
    that passed in an older build does not count). Default is global-latest.
    """
    async with _session() as s:
        return await plans.get_run_manifest(s, plan_id, build_id)


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

    Transport is chosen via AQA_MCP_TRANSPORT (default 'stdio' — the client
    spawns this process). Set it to 'streamable-http' (or 'sse') to run a
    long-lived networked server other agents connect to over a URL; host/port
    come from AQA_MCP_HOST / AQA_MCP_PORT (default 127.0.0.1:8001).
    """

    transport = _env("AQA_MCP_TRANSPORT", "stdio")
    if transport != "stdio":
        mcp.settings.host = _env("AQA_MCP_HOST", "127.0.0.1")
        mcp.settings.port = int(_env("AQA_MCP_PORT", "8001"))
        mcp.run(transport=transport)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
