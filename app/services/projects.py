from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.structure import Project
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.errors import Conflict, NotFound


async def create_project(session: AsyncSession, data: ProjectCreate) -> Project:
    existing = (
        await session.execute(select(Project).where(Project.prefix == data.prefix))
    ).scalar_one_or_none()
    if existing:
        raise Conflict(f"project prefix '{data.prefix}' already exists")
    project = Project(name=data.name, prefix=data.prefix, options=data.options)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def get_project(session: AsyncSession, project_id: int) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFound(f"project {project_id} not found")
    return project


async def list_projects(session: AsyncSession, active: bool | None = None) -> list[Project]:
    stmt = select(Project).order_by(Project.id)
    if active is not None:
        stmt = stmt.where(Project.active == active)
    return list((await session.execute(stmt)).scalars().all())


async def update_project(session: AsyncSession, project_id: int, data: ProjectUpdate) -> Project:
    project = await get_project(session, project_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    return project
