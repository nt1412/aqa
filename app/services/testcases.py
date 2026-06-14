from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.structure import Project, TestSuite
from app.models.testcase import TestCase, TestCaseVersion, TestStep
from app.schemas.testcase import TestCaseCreate, VersionCreate
from app.services.errors import NotFound


async def _load_full(session: AsyncSession, case_id: int) -> TestCase:
    stmt = (
        select(TestCase)
        .where(TestCase.id == case_id)
        .options(selectinload(TestCase.versions).selectinload(TestCaseVersion.steps))
        .execution_options(populate_existing=True)
    )
    tc = (await session.execute(stmt)).scalar_one_or_none()
    if tc is None:
        raise NotFound(f"test case {case_id} not found")
    return tc


def _current_version(tc: TestCase) -> TestCaseVersion | None:
    active = [v for v in tc.versions if v.active]
    return max(active, key=lambda v: v.version) if active else None


async def create_test_case(session: AsyncSession, suite_id: int, data: TestCaseCreate) -> TestCase:
    suite = await session.get(TestSuite, suite_id)
    if suite is None:
        raise NotFound(f"suite {suite_id} not found")
    project = await session.get(Project, suite.project_id)
    project.tc_counter += 1
    external_id = f"{project.prefix}-{project.tc_counter}"

    tc = TestCase(
        suite_id=suite_id,
        project_id=project.id,
        external_id=external_id,
        name=data.name,
    )
    session.add(tc)
    await session.flush()

    version = TestCaseVersion(
        case_id=tc.id,
        version=1,
        summary=data.summary,
        preconditions=data.preconditions,
        importance=data.importance,
        execution_type=data.execution_type,
        estimated_duration=data.estimated_duration,
    )
    session.add(version)
    await session.flush()

    for i, step in enumerate(data.steps, start=1):
        session.add(
            TestStep(
                version_id=version.id,
                step_number=i,
                action=step.action,
                expected_result=step.expected_result,
                execution_type=step.execution_type,
            )
        )
    await session.commit()
    return await _load_full(session, tc.id)


async def create_version(
    session: AsyncSession, case_id: int, data: VersionCreate
) -> TestCaseVersion:
    tc = await _load_full(session, case_id)
    latest = _current_version(tc)
    if latest is None:
        raise NotFound(f"test case {case_id} has no active version")

    new_version = TestCaseVersion(
        case_id=case_id,
        version=latest.version + 1,
        summary=data.summary if data.summary is not None else latest.summary,
        preconditions=data.preconditions
        if data.preconditions is not None
        else latest.preconditions,
        importance=data.importance if data.importance is not None else latest.importance,
        execution_type=data.execution_type
        if data.execution_type is not None
        else latest.execution_type,
    )
    session.add(new_version)
    await session.flush()

    source_steps = (
        [
            TestStep(
                action=s.action, expected_result=s.expected_result, execution_type=s.execution_type
            )
            for s in data.steps
        ]
        if data.steps is not None
        else [
            TestStep(
                action=s.action, expected_result=s.expected_result, execution_type=s.execution_type
            )
            for s in latest.steps
        ]
    )
    for i, s in enumerate(source_steps, start=1):
        s.version_id = new_version.id
        s.step_number = i
        session.add(s)
    await session.commit()
    await session.refresh(new_version)
    return new_version


async def get_test_case(session: AsyncSession, case_id: int):
    tc = await _load_full(session, case_id)
    from app.schemas.testcase import TestCaseOut, VersionOut

    out = TestCaseOut.model_validate(tc)
    cur = _current_version(tc)
    out.current_version = VersionOut.model_validate(cur) if cur else None
    return out


async def get_by_external_id(session: AsyncSession, project_id: int, external_id: str):
    stmt = select(TestCase).where(
        TestCase.project_id == project_id, TestCase.external_id == external_id
    )
    tc = (await session.execute(stmt)).scalar_one_or_none()
    if tc is None:
        raise NotFound(f"test case '{external_id}' not found")
    return await get_test_case(session, tc.id)


async def search_test_cases(session: AsyncSession, project_id: int, query: str) -> list[TestCase]:
    stmt = (
        select(TestCase)
        .where(
            TestCase.project_id == project_id,
            TestCase.name.ilike(f"%{query}%"),
        )
        .order_by(TestCase.id)
    )
    return list((await session.execute(stmt)).scalars().all())
