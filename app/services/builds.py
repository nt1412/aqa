from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Build
from app.schemas.plan import BuildCreate
from app.services.errors import NotFound
from app.services.plans import get_plan


async def create_build(session: AsyncSession, plan_id: int, data: BuildCreate) -> Build:
    """Find-or-create by (plan_id, name); backfill metadata on existing builds.

    Mirrors executions._upsert_build so the explicit API and execution-time
    upsert agree on the unique (plan_id, name) constraint.
    """
    await get_plan(session, plan_id)  # raises NotFound if absent
    existing = (
        await session.execute(
            select(Build).where(Build.plan_id == plan_id, Build.name == data.name)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if data.commit_id and not existing.commit_id:
            existing.commit_id = data.commit_id
        if data.tag and not existing.tag:
            existing.tag = data.tag
        if data.branch and not existing.branch:
            existing.branch = data.branch
        await session.commit()
        await session.refresh(existing)
        return existing
    build = Build(
        plan_id=plan_id,
        name=data.name,
        notes=data.notes,
        tag=data.tag,
        branch=data.branch,
        commit_id=data.commit_id,
    )
    session.add(build)
    await session.commit()
    await session.refresh(build)
    return build


async def get_build(session: AsyncSession, build_id: int) -> Build:
    build = await session.get(Build, build_id)
    if build is None:
        raise NotFound(f"build {build_id} not found")
    return build


async def list_builds(session: AsyncSession, plan_id: int) -> list[Build]:
    stmt = select(Build).where(Build.plan_id == plan_id).order_by(Build.id)
    return list((await session.execute(stmt)).scalars().all())
