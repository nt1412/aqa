import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.execution import Execution, ExecutionStep
from app.models.plan import Build, TestPlan, TestPlanCase
from app.models.testcase import TestCase, TestCaseVersion, TestStep
from app.schemas.execution import ExecutionCreate
from app.services.errors import NotFound, ValidationFailed
from app.services.evidence import record_claims_and_reasoning
from app.services.testcases import get_dependents

logger = logging.getLogger(__name__)


async def _resolve_case(session: AsyncSession, data: ExecutionCreate) -> TestCase:
    if data.case_id is not None:
        tc = await session.get(TestCase, data.case_id)
        if tc is None:
            raise NotFound(f"test case {data.case_id} not found")
        return tc
    if data.external_id is not None and data.project_id is not None:
        stmt = select(TestCase).where(
            TestCase.project_id == data.project_id,
            TestCase.external_id == data.external_id,
        )
        tc = (await session.execute(stmt)).scalar_one_or_none()
        if tc is None:
            raise NotFound(f"test case '{data.external_id}' not found")
        return tc
    raise ValidationFailed("provide case_id, or external_id + project_id")


async def _current_version_id(session: AsyncSession, case_id: int) -> int:
    stmt = (
        select(TestCaseVersion)
        .where(TestCaseVersion.case_id == case_id, TestCaseVersion.active.is_(True))
        .order_by(TestCaseVersion.version.desc())
    )
    v = (await session.execute(stmt)).scalars().first()
    if v is None:
        raise NotFound(f"test case {case_id} has no active version")
    return v.id


async def _upsert_build(
    session: AsyncSession,
    plan_id: int | None,
    build_name: str,
    commit_id: str | None,
    branch: str | None = None,
    base_commit: str | None = None,
) -> int | None:
    if plan_id is None:
        return None
    plan = await session.get(TestPlan, plan_id)
    if plan is None:
        raise NotFound(f"test plan {plan_id} not found")
    stmt = select(Build).where(Build.plan_id == plan_id, Build.name == build_name)
    build = (await session.execute(stmt)).scalar_one_or_none()
    if build is None:
        build = Build(
            plan_id=plan_id,
            name=build_name,
            commit_id=commit_id,
            branch=branch,
            base_commit=base_commit,
        )
        session.add(build)
        await session.flush()
    else:
        # backfill once: the first recorder to supply each field wins, later runs
        # for the same (plan, build_name) don't clobber it.
        if commit_id and not build.commit_id:
            build.commit_id = commit_id
        if branch and not build.branch:
            build.branch = branch
        if base_commit and not build.base_commit:
            build.base_commit = base_commit
    return build.id


async def _transitive_dependents(session: AsyncSession, case_id: int) -> list[int]:
    """All cases downstream of case_id via depends_on edges (BFS; graph is a DAG)."""
    seen: set[int] = set()
    order: list[int] = []
    stack = [case_id]
    while stack:
        for dep in await get_dependents(session, stack.pop()):
            if dep not in seen:
                seen.add(dep)
                order.append(dep)
                stack.append(dep)
    return order


async def _cascade_block(
    session: AsyncSession, trigger_case_id: int, trigger_external_id: str,
    plan_id: int, build_id: int | None, tester_id: int | None,
) -> list[int]:
    """Record a blocked execution for each in-plan downstream case of a failed
    prerequisite, so a regression run reflects what can't be trusted. Skips any
    case already recorded for this build (never overrides a real result)."""
    downstream = await _transitive_dependents(session, trigger_case_id)
    if not downstream:
        return []
    members = set(
        (
            await session.execute(
                select(TestCase.id)
                .join(TestCaseVersion, TestCaseVersion.case_id == TestCase.id)
                .join(TestPlanCase, TestPlanCase.version_id == TestCaseVersion.id)
                .where(TestPlanCase.plan_id == plan_id)
            )
        )
        .scalars()
        .all()
    )
    blocked: list[int] = []
    for cid in downstream:
        if cid not in members:
            continue
        already = (
            await session.execute(
                select(Execution.id)
                .join(TestCaseVersion, TestCaseVersion.id == Execution.version_id)
                .where(TestCaseVersion.case_id == cid, Execution.build_id == build_id)
            )
        ).first()
        if already is not None:
            continue
        session.add(
            Execution(
                plan_id=plan_id,
                version_id=await _current_version_id(session, cid),
                build_id=build_id,
                tester_id=tester_id,
                execution_type="automated",
                status="blocked",
                notes=f"auto-blocked: prerequisite {trigger_external_id} did not pass",
            )
        )
        blocked.append(cid)
    if blocked:
        await session.commit()
    return blocked


async def record_execution(
    session: AsyncSession,
    data: ExecutionCreate,
    tester_id: int | None,
    cascade: bool = False,
) -> Execution:
    case = await _resolve_case(session, data)
    case_id, case_external_id = case.id, case.external_id  # capture before commit expires them
    version_id = await _current_version_id(session, case.id)
    build_id = await _upsert_build(
        session, data.plan_id, data.build_name, data.commit_id, data.branch, data.base_commit
    )

    execution = Execution(
        plan_id=data.plan_id,
        version_id=version_id,
        build_id=build_id,
        tester_id=tester_id,
        execution_type="automated" if tester_id is None else "manual",
        status=data.status,
        notes=data.notes,
        duration=data.duration,
        session_id=data.session_id,
        run_id=data.run_id,
    )
    session.add(execution)
    await session.flush()

    if data.step_results:
        steps = (
            (await session.execute(select(TestStep).where(TestStep.version_id == version_id)))
            .scalars()
            .all()
        )
        by_number = {s.step_number: s.id for s in steps}
        for sr in data.step_results:
            step_id = by_number.get(sr.step_number)
            if step_id is None:
                raise ValidationFailed(f"step_number {sr.step_number} not in current version")
            session.add(
                ExecutionStep(
                    execution_id=execution.id,
                    step_id=step_id,
                    status=sr.status,
                    notes=sr.notes,
                )
            )
    await record_claims_and_reasoning(
        session,
        execution.id,
        data.claims,
        data.reasoning,
        data.agent_model,
        data.session_id,
        notes=data.notes,
        claimant_id=tester_id,
    )
    execution_id = execution.id
    await session.commit()  # primary result is now durable
    if cascade and data.status in ("fail", "blocked") and data.plan_id is not None:
        # Best-effort bookkeeping: the primary execution is already committed, so a
        # cascade failure must NOT propagate (it would make the caller think the
        # record failed and retry, duplicating the primary). Degrade gracefully.
        try:
            await _cascade_block(
                session, case_id, case_external_id, data.plan_id, build_id, tester_id
            )
        except Exception:
            await session.rollback()  # discard any partial cascade writes
            logger.warning("cascade-block failed for execution %s", execution_id, exc_info=True)
    return await _load(session, execution_id)


async def _attach_case_ids(session: AsyncSession, executions: list[Execution]) -> None:
    """Set a non-mapped ``case_id`` on each execution (resolved via its version).

    ExecutionOut reads it via from_attributes; the default keeps any read path
    that skips this helper safe. Call after the final load with no commit after,
    or expire-on-commit would invalidate the attribute.
    """
    version_ids = {e.version_id for e in executions}
    if not version_ids:
        return
    rows = (
        await session.execute(
            select(TestCaseVersion.id, TestCaseVersion.case_id).where(
                TestCaseVersion.id.in_(version_ids)
            )
        )
    ).all()
    by_version = {vid: cid for vid, cid in rows}
    for e in executions:
        e.case_id = by_version.get(e.version_id)


async def _load(session: AsyncSession, execution_id: int) -> Execution:
    stmt = (
        select(Execution).where(Execution.id == execution_id).options(selectinload(Execution.steps))
    )
    ex = (await session.execute(stmt)).scalar_one_or_none()
    if ex is None:
        raise NotFound(f"execution {execution_id} not found")
    await _attach_case_ids(session, [ex])
    return ex


async def get_execution(session: AsyncSession, execution_id: int) -> Execution:
    return await _load(session, execution_id)


async def list_for_case(session: AsyncSession, case_id: int) -> list[Execution]:
    version_ids = (
        (
            await session.execute(
                select(TestCaseVersion.id).where(TestCaseVersion.case_id == case_id)
            )
        )
        .scalars()
        .all()
    )
    if not version_ids:
        return []
    stmt = (
        select(Execution)
        .where(Execution.version_id.in_(version_ids))
        .order_by(Execution.created_at.desc())
        .options(selectinload(Execution.steps))
    )
    execs = list((await session.execute(stmt)).scalars().all())
    await _attach_case_ids(session, execs)
    return execs


async def list_for_plan(session: AsyncSession, plan_id: int) -> list[Execution]:
    stmt = (
        select(Execution)
        .where(Execution.plan_id == plan_id)
        .order_by(Execution.created_at.desc())
        .options(selectinload(Execution.steps))
    )
    execs = list((await session.execute(stmt)).scalars().all())
    await _attach_case_ids(session, execs)
    return execs
