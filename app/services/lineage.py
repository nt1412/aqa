"""Compute-on-read lineage aggregations over the ``latest_result_per_build_case``
view (see ``app/db_views.py``). Build/commit/run rollups, build detail, and
per-case history — the data spine for the operator console.
"""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Build, TestPlanCase
from app.models.testcase import TestCaseVersion
from app.services.builds import get_build, list_builds
from app.services.plans import get_plan
from app.services.projects import get_project

DEFAULT_BRANCH_FALLBACK = "main"


def _build_dump(build: Build) -> dict:
    return {
        "id": build.id,
        "plan_id": build.plan_id,
        "name": build.name,
        "branch": build.branch,
        "commit_id": build.commit_id,
        "base_commit": build.base_commit,
        "created_at": build.created_at.isoformat() if build.created_at else None,
    }


async def _plan_case_ids(session: AsyncSession, plan_id: int) -> set[int]:
    """Distinct test-case ids that are in a plan (across any linked version)."""
    rows = (
        await session.execute(
            select(TestCaseVersion.case_id)
            .join(TestPlanCase, TestPlanCase.version_id == TestCaseVersion.id)
            .where(TestPlanCase.plan_id == plan_id)
        )
    ).scalars().all()
    return set(rows)


async def _latest_results(session: AsyncSession, build_id: int) -> dict[int, str]:
    """case_id -> latest status in this build, from the single-definition view."""
    rows = (
        await session.execute(
            text(
                "SELECT case_id, status FROM latest_result_per_build_case "
                "WHERE build_id = :b"
            ),
            {"b": build_id},
        )
    ).all()
    return {case_id: status for case_id, status in rows}


async def build_rollup(session: AsyncSession, build_id: int) -> dict:
    """Pass/fail/blocked/not_run counts + pass_rate for one build.

    Counts are over the LATEST result per case in the build (so a case run twice
    counts once). ``not_run`` is plan cases with no result in this build;
    ``pass_rate`` is pass / plan_cases (a build that skipped half the plan is not
    100% just because what ran passed).
    """
    build = await get_build(session, build_id)  # raises NotFound
    results = await _latest_results(session, build_id)
    plan_case_ids = await _plan_case_ids(session, build.plan_id)

    passed = sum(1 for s in results.values() if s == "pass")
    failed = sum(1 for s in results.values() if s == "fail")
    blocked = sum(1 for s in results.values() if s == "blocked")
    not_run = sum(1 for cid in plan_case_ids if cid not in results)
    plan_cases = len(plan_case_ids)
    pass_rate = round(100 * passed / plan_cases) if plan_cases else 0
    return {
        "build_id": build_id,
        "plan_id": build.plan_id,
        "pass": passed,
        "fail": failed,
        "blocked": blocked,
        "not_run": not_run,
        "executed": len(results),
        "plan_cases": plan_cases,
        "pass_rate": pass_rate,
    }


async def build_detail(session: AsyncSession, build_id: int) -> dict:
    """Build header + rollup + each case's LATEST result in the build."""
    build = await get_build(session, build_id)
    rollup = await build_rollup(session, build_id)
    rows = (
        await session.execute(
            text(
                "SELECT r.case_id, r.status, r.execution_id, r.duration, "
                "       c.external_id, c.name "
                "FROM latest_result_per_build_case r "
                "JOIN test_cases c ON c.id = r.case_id "
                "WHERE r.build_id = :b ORDER BY c.external_id"
            ),
            {"b": build_id},
        )
    ).all()
    cases = [
        {
            "case_id": cid,
            "status": status,
            "execution_id": eid,
            "duration": duration,
            "external_id": ext,
            "name": name,
        }
        for cid, status, eid, duration, ext, name in rows
    ]
    return {"build": _build_dump(build), "rollup": rollup, "cases": cases}


async def case_history(session: AsyncSession, case_id: int) -> dict:
    """A case's latest result per build, chronological, with derived broke/fixed
    transitions (pass→fail = broke at that commit; fail/blocked→pass = fixed).
    The transitions are the "known regression path" the guard later surfaces.
    """
    rows = (
        await session.execute(
            text(
                "SELECT r.build_id, b.name, b.branch, b.commit_id, r.status, "
                "       r.execution_id, b.created_at "
                "FROM latest_result_per_build_case r "
                "JOIN builds b ON b.id = r.build_id "
                "WHERE r.case_id = :c ORDER BY b.created_at, b.id"
            ),
            {"c": case_id},
        )
    ).all()
    executions = [
        {
            "build_id": bid,
            "build_name": bname,
            "branch": branch,
            "commit_id": commit_id,
            "status": status,
            "execution_id": eid,
            "created_at": created_at.isoformat() if created_at else None,
        }
        for bid, bname, branch, commit_id, status, eid, created_at in rows
    ]
    transitions: list[dict] = []
    prev = None
    for e in executions:
        if prev is not None:
            if prev["status"] == "pass" and e["status"] in ("fail", "blocked"):
                transitions.append(
                    {"type": "broke", "commit_id": e["commit_id"], "build_id": e["build_id"]}
                )
            elif prev["status"] in ("fail", "blocked") and e["status"] == "pass":
                transitions.append(
                    {"type": "fixed", "commit_id": e["commit_id"], "build_id": e["build_id"]}
                )
        prev = e
    return {"case_id": case_id, "executions": executions, "transitions": transitions}


async def default_branch_for_plan(session: AsyncSession, plan_id: int) -> str:
    plan = await get_plan(session, plan_id)
    project = await get_project(session, plan.project_id)
    return (project.options or {}).get("default_branch", DEFAULT_BRANCH_FALLBACK)


async def resolve_baseline(session: AsyncSession, build: Build) -> Build | None:
    """The default-branch build (in the same plan) this branch build is judged
    against. Precise when base_commit matches a default-branch build; otherwise
    the latest default-branch build at or before this build's created_at. None
    when there is no default-branch build to compare against (→ "all new").
    """
    default_branch = await default_branch_for_plan(session, build.plan_id)
    candidates = (
        await session.execute(
            select(Build).where(
                Build.plan_id == build.plan_id,
                Build.branch == default_branch,
                Build.id != build.id,
            )
        )
    ).scalars().all()
    if not candidates:
        return None
    # precise: pin to the recorded merge-base if that build exists
    if build.base_commit:
        for c in candidates:
            if c.commit_id == build.base_commit:
                return c
    # fallback: latest default-branch build at/before this build's time
    eligible = [
        c for c in candidates
        if c.created_at and build.created_at and c.created_at <= build.created_at
    ] or candidates
    eligible.sort(key=lambda c: (c.created_at, c.id))
    return eligible[-1]


async def _case_meta(session: AsyncSession, case_ids: set[int]) -> dict[int, tuple]:
    if not case_ids:
        return {}
    rows = (
        await session.execute(
            text(
                "SELECT id, external_id, name FROM test_cases WHERE id = ANY(:ids)"
            ),
            {"ids": list(case_ids)},
        )
    ).all()
    return {cid: (ext, name) for cid, ext, name in rows}


_DIFF_CLASSES = (
    "regression",
    "fixed",
    "still_failing",
    "still_passing",
    "new_test",
    "removed",
)


def _classify(baseline_status: str | None, build_status: str | None) -> str:
    if baseline_status is None and build_status is not None:
        return "new_test"  # new coverage on this branch — NOT a regression
    if build_status is None and baseline_status is not None:
        return "removed"
    if baseline_status == "pass" and build_status in ("fail", "blocked"):
        return "regression"  # you broke it
    if baseline_status in ("fail", "blocked") and build_status == "pass":
        return "fixed"
    if baseline_status in ("fail", "blocked") and build_status in ("fail", "blocked"):
        return "still_failing"
    return "still_passing"


async def compare(session: AsyncSession, build_id: int, to: int | str = "baseline") -> dict:
    """Classify each case between a build and another build (or its baseline).

    ``to`` is a build id, or "baseline" to auto-resolve the default-branch build.
    Each case is exactly one of: regression / fixed / still_failing /
    still_passing / new_test / removed. A regression (baseline pass → fail) is
    never conflated with a new_test (no baseline result).
    """
    build = await get_build(session, build_id)
    if to == "baseline":
        baseline = await resolve_baseline(session, build)
    else:
        baseline = await get_build(session, int(to))
    cur = await _latest_results(session, build_id)
    base = await _latest_results(session, baseline.id) if baseline else {}

    classes: dict[str, list] = {k: [] for k in _DIFF_CLASSES}
    meta = await _case_meta(session, set(cur) | set(base))
    for cid in sorted(set(cur) | set(base), key=lambda x: meta.get(x, ("", ""))[0]):
        b_status = cur.get(cid)
        a_status = base.get(cid)
        ext, name = meta.get(cid, (None, None))
        classes[_classify(a_status, b_status)].append(
            {
                "case_id": cid,
                "external_id": ext,
                "name": name,
                "baseline_status": a_status,
                "build_status": b_status,
            }
        )
    return {
        "build_id": build_id,
        "baseline_build_id": baseline.id if baseline else None,
        "classes": classes,
    }


async def list_builds_enriched(session: AsyncSession, plan_id: int) -> list[dict]:
    """Builds for a plan, newest first, each with its rollup — the build timeline."""
    builds = await list_builds(session, plan_id)
    ordered = sorted(builds, key=lambda b: (b.created_at, b.id), reverse=True)
    out: list[dict] = []
    for b in ordered:
        d = _build_dump(b)
        d["rollup"] = await build_rollup(session, b.id)
        out.append(d)
    return out
