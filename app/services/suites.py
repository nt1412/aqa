from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.structure import TestSuite
from app.schemas.suite import SuiteCreate, SuiteNode
from app.services.errors import NotFound
from app.services.projects import get_project


async def create_suite(session: AsyncSession, project_id: int, data: SuiteCreate) -> TestSuite:
    await get_project(session, project_id)  # raises NotFound if absent
    if data.parent_id is not None:
        parent = await session.get(TestSuite, data.parent_id)
        if parent is None or parent.project_id != project_id:
            raise NotFound(f"parent suite {data.parent_id} not found in project")
    suite = TestSuite(
        project_id=project_id, parent_id=data.parent_id, name=data.name, details=data.details
    )
    session.add(suite)
    await session.commit()
    await session.refresh(suite)
    return suite


async def get_suite(session: AsyncSession, suite_id: int) -> TestSuite:
    suite = await session.get(TestSuite, suite_id)
    if suite is None:
        raise NotFound(f"suite {suite_id} not found")
    return suite


async def list_suites(session: AsyncSession, project_id: int) -> list[TestSuite]:
    stmt = select(TestSuite).where(TestSuite.project_id == project_id).order_by(TestSuite.id)
    return list((await session.execute(stmt)).scalars().all())


async def find_or_create_path(session: AsyncSession, project_id: int, path: str) -> TestSuite:
    """Resolve a slash-delimited path, creating any missing suites. Returns the leaf."""
    await get_project(session, project_id)
    parts = [p.strip() for p in path.split("/") if p.strip()]
    if not parts:
        raise NotFound("empty suite path")
    parent_id: int | None = None
    current: TestSuite | None = None
    for name in parts:
        stmt = select(TestSuite).where(
            TestSuite.project_id == project_id,
            TestSuite.parent_id.is_(parent_id)
            if parent_id is None
            else TestSuite.parent_id == parent_id,
            TestSuite.name == name,
        )
        current = (await session.execute(stmt)).scalar_one_or_none()
        if current is None:
            current = TestSuite(project_id=project_id, parent_id=parent_id, name=name)
            session.add(current)
            await session.flush()
        parent_id = current.id
    await session.commit()
    await session.refresh(current)
    return current


async def get_tree(session: AsyncSession, project_id: int) -> list[SuiteNode]:
    suites = await list_suites(session, project_id)
    nodes: dict[int, SuiteNode] = {s.id: SuiteNode.model_validate(s) for s in suites}
    roots: list[SuiteNode] = []
    for s in suites:
        node = nodes[s.id]
        if s.parent_id is None:
            roots.append(node)
        else:
            nodes[s.parent_id].children.append(node)
    return roots
