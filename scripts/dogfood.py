"""Dogfood: catalog AQA's own pytest suite inside AQA, and record a run.

This closes the loop project -> suites -> versioned cases -> execution against a
plan+build, using the real service layer. It is idempotent: re-running reuses the
AQA project, suites, and cases (so it survives the unique constraints on
project prefix and (project_id, external_id)), and appends one fresh execution
per case for the current git build.

Phase 2a gap is now closed: the plan is created through the public `plans` service
(`app.services.plans.create_plan` / `list_plans`) rather than via the ORM directly.
An agent restricted to MCP/REST can now create the plan through the public API.
Executions are recorded through `executions.record_execution` (which upserts the
build by name).

Data is written to the dev database (app.db.SessionLocal), in a self-contained
`AQA` project (prefix AQA), independent of scripts/seed.py defaults.

Usage:
    python -m pytest --junitxml=dogfood-results.xml   # produce real results
    python -m scripts.dogfood                          # catalog + record run
"""

import asyncio
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models.structure import Project
from app.models.testcase import TestCase, TestCaseScriptLink, TestCaseVersion
from app.schemas.execution import ExecutionCreate
from app.schemas.project import ProjectCreate
from app.schemas.testcase import TestCaseCreate
from app.services import executions, projects, suites, testcases

PROJECT_NAME = "AQA"
PROJECT_PREFIX = "AQA"
PLAN_NAME = "CI"
REPO = "aqa"
JUNIT_PATH = Path("dogfood-results.xml")


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _parse_junit(path: Path) -> list[dict]:
    """Return one dict per test: {suite, name, nodeid, status}."""
    tree = ET.parse(path)
    results = []
    for tc in tree.findall(".//testcase"):
        classname = tc.get("classname", "")  # e.g. "tests.test_auth"
        name = tc.get("name", "")
        module_path = classname.replace(".", "/") + ".py"  # tests/test_auth.py
        suite = classname.rsplit(".", 1)[-1].removeprefix("test_")  # "auth"
        nodeid = f"{module_path}::{name}"
        child_tags = {child.tag for child in tc}
        if "failure" in child_tags or "error" in child_tags:
            status = "fail"
        elif "skipped" in child_tags:
            status = "not_run"
        else:
            status = "pass"
        results.append({"suite": suite, "name": name, "nodeid": nodeid, "status": status})
    return results


async def _get_or_create_project(session: AsyncSession) -> Project:
    proj = (
        await session.execute(select(Project).where(Project.prefix == PROJECT_PREFIX))
    ).scalar_one_or_none()
    if proj is None:
        proj = await projects.create_project(
            session, ProjectCreate(name=PROJECT_NAME, prefix=PROJECT_PREFIX)
        )
    return proj


async def _get_or_create_case(
    session: AsyncSession,
    project_id: int,
    suite_id: int,
    name: str,
    nodeid: str,
    sha: str,
    branch: str,
) -> TestCase:
    existing = (
        await session.execute(
            select(TestCase).where(
                TestCase.project_id == project_id,
                TestCase.suite_id == suite_id,
                TestCase.name == name,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    tc = await testcases.create_test_case(
        session,
        suite_id,
        # pytest tests are atomic — no fabricated steps; record as automated.
        TestCaseCreate(name=name, summary=nodeid, execution_type="automated"),
    )
    current = (
        (
            await session.execute(
                select(TestCaseVersion)
                .where(TestCaseVersion.case_id == tc.id)
                .order_by(TestCaseVersion.version.desc())
            )
        )
        .scalars()
        .first()
    )
    session.add(
        TestCaseScriptLink(
            version_id=current.id, repo=REPO, branch=branch, path=nodeid, commit_id=sha
        )
    )
    await session.commit()
    return tc


async def _get_or_create_plan(session: AsyncSession, project_id: int):
    from app.schemas.plan import PlanCreate
    from app.services import plans

    for existing in await plans.list_plans(session, project_id):
        if existing.name == PLAN_NAME:
            return existing
    return await plans.create_plan(session, project_id, PlanCreate(name=PLAN_NAME))


async def main() -> None:
    if not JUNIT_PATH.exists():
        raise SystemExit(f"{JUNIT_PATH} not found — run: python -m pytest --junitxml={JUNIT_PATH}")
    sha = _git("rev-parse", "--short", "HEAD")
    full_sha = _git("rev-parse", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    tests = _parse_junit(JUNIT_PATH)

    async with SessionLocal() as session:
        project = await _get_or_create_project(session)
        plan = await _get_or_create_plan(session, project.id)

        suite_ids: dict[str, int] = {}
        recorded = 0
        for t in tests:
            if t["suite"] not in suite_ids:
                suite = await suites.find_or_create_path(session, project.id, t["suite"])
                suite_ids[t["suite"]] = suite.id
            case = await _get_or_create_case(
                session, project.id, suite_ids[t["suite"]], t["name"], t["nodeid"], sha, branch
            )
            await executions.record_execution(
                session,
                ExecutionCreate(
                    case_id=case.id,
                    plan_id=plan.id,
                    build_name=sha,
                    commit_id=full_sha,
                    status=t["status"],
                ),
                tester_id=None,
            )
            recorded += 1

        # Close the loop: query results back through the service layer.
        runs = await executions.list_for_plan(session, plan.id)
        passed = sum(1 for r in runs if r.status == "pass")
        failed = sum(1 for r in runs if r.status == "fail")

    print(f"project={PROJECT_NAME} (#{project.id})  plan={PLAN_NAME} (#{plan.id})  build={sha}")
    print(f"suites={len(suite_ids)}  cases_catalogued={recorded}")
    print(f"executions_for_plan={len(runs)}  pass={passed}  fail={failed}")


if __name__ == "__main__":
    asyncio.run(main())
