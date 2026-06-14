from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.requirement import ReqCoverage, ReqSpec, Requirement, ReqVersion
from app.models.testcase import TestCaseVersion
from app.schemas.requirement import (
    CoverageGap,
    ReqSpecCreate,
    RequirementCreate,
    RequirementOut,
    ReqVersionOut,
    TraceabilityRow,
)
from app.services.errors import NotFound
from app.services.plans import _current_version_id
from app.services.projects import get_project


async def create_req_spec(session: AsyncSession, project_id: int, data: ReqSpecCreate) -> ReqSpec:
    await get_project(session, project_id)
    spec = ReqSpec(project_id=project_id, doc_id=data.doc_id, name=data.name, scope=data.scope)
    session.add(spec)
    await session.commit()
    await session.refresh(spec)
    return spec


async def list_req_specs(session: AsyncSession, project_id: int) -> list[ReqSpec]:
    stmt = select(ReqSpec).where(ReqSpec.project_id == project_id).order_by(ReqSpec.id)
    return list((await session.execute(stmt)).scalars().all())


async def create_requirement(session: AsyncSession, spec_id: int, data: RequirementCreate):
    spec = await session.get(ReqSpec, spec_id)
    if spec is None:
        raise NotFound(f"req spec {spec_id} not found")
    req = Requirement(spec_id=spec_id, req_doc_id=data.req_doc_id, name=data.name)
    session.add(req)
    await session.flush()
    version = ReqVersion(req_id=req.id, version=1, scope=data.scope, status="draft")
    session.add(version)
    await session.flush()

    if data.link_to_cases:
        from app.services.requirements import link_coverage

        await link_coverage(session, version.id, data.link_to_cases)
    await session.commit()
    return await get_requirement(session, req.id)


async def _current_req_version(session: AsyncSession, req: Requirement) -> ReqVersion | None:
    stmt = select(ReqVersion).where(ReqVersion.req_id == req.id).order_by(ReqVersion.version.desc())
    return (await session.execute(stmt)).scalars().first()


async def get_requirement(session: AsyncSession, req_id: int) -> RequirementOut:
    req = await session.get(Requirement, req_id)
    if req is None:
        raise NotFound(f"requirement {req_id} not found")
    out = RequirementOut.model_validate(req)
    cur = await _current_req_version(session, req)
    out.current_version = ReqVersionOut.model_validate(cur) if cur else None
    return out


async def list_requirements(session: AsyncSession, spec_id: int) -> list[Requirement]:
    stmt = select(Requirement).where(Requirement.spec_id == spec_id).order_by(Requirement.id)
    return list((await session.execute(stmt)).scalars().all())


async def link_coverage(
    session: AsyncSession, req_version_id: int, case_ids: list[int]
) -> list[ReqCoverage]:
    created: list[ReqCoverage] = []
    for case_id in case_ids:
        case_version_id = await _current_version_id(session, case_id)
        existing = (
            await session.execute(
                select(ReqCoverage).where(
                    ReqCoverage.req_version_id == req_version_id,
                    ReqCoverage.case_version_id == case_version_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            created.append(existing)
            continue
        cov = ReqCoverage(
            req_version_id=req_version_id, case_version_id=case_version_id, is_active=True
        )
        session.add(cov)
        await session.flush()
        created.append(cov)
    return created


async def link_requirement_coverage(
    session: AsyncSession, req_id: int, case_ids: list[int]
) -> list[ReqCoverage]:
    req = await session.get(Requirement, req_id)
    if req is None:
        raise NotFound(f"requirement {req_id} not found")
    version = await _current_req_version(session, req)
    if version is None:
        raise NotFound(f"requirement {req_id} has no version")
    links = await link_coverage(session, version.id, case_ids)
    await session.commit()
    return links


async def get_coverage_gaps(
    session: AsyncSession, project_id: int, spec_id: int | None = None
) -> list[CoverageGap]:
    # current req version per requirement in the project, with no active coverage
    spec_stmt = select(ReqSpec.id).where(ReqSpec.project_id == project_id)
    if spec_id is not None:
        spec_stmt = spec_stmt.where(ReqSpec.id == spec_id)
    spec_ids = (await session.execute(spec_stmt)).scalars().all()
    if not spec_ids:
        return []
    reqs = (
        (await session.execute(select(Requirement).where(Requirement.spec_id.in_(spec_ids))))
        .scalars()
        .all()
    )

    gaps: list[CoverageGap] = []
    for req in reqs:
        version = await _current_req_version(session, req)
        if version is None:
            continue
        covered = (
            await session.execute(
                select(ReqCoverage.id).where(
                    ReqCoverage.req_version_id == version.id,
                    ReqCoverage.is_active.is_(True),
                )
            )
        ).first()
        if covered is None:
            gaps.append(
                CoverageGap(
                    requirement_id=req.id,
                    req_version_id=version.id,
                    req_doc_id=req.req_doc_id,
                    name=req.name,
                )
            )
    return gaps


async def get_traceability(
    session: AsyncSession, project_id: int, spec_id: int | None = None
) -> list[TraceabilityRow]:
    spec_stmt = select(ReqSpec.id).where(ReqSpec.project_id == project_id)
    if spec_id is not None:
        spec_stmt = spec_stmt.where(ReqSpec.id == spec_id)
    spec_ids = (await session.execute(spec_stmt)).scalars().all()
    if not spec_ids:
        return []
    reqs = (
        (
            await session.execute(
                select(Requirement)
                .where(Requirement.spec_id.in_(spec_ids))
                .order_by(Requirement.id)
            )
        )
        .scalars()
        .all()
    )

    rows: list[TraceabilityRow] = []
    for req in reqs:
        version = await _current_req_version(session, req)
        case_ids: list[int] = []
        if version is not None:
            # coverage -> case_version -> case
            cov_case_ids = (
                (
                    await session.execute(
                        select(TestCaseVersion.case_id)
                        .join(ReqCoverage, ReqCoverage.case_version_id == TestCaseVersion.id)
                        .where(
                            ReqCoverage.req_version_id == version.id,
                            ReqCoverage.is_active.is_(True),
                        )
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )
            case_ids = list(cov_case_ids)
        rows.append(
            TraceabilityRow(
                requirement_id=req.id,
                req_doc_id=req.req_doc_id,
                name=req.name,
                covered_case_ids=case_ids,
            )
        )
    return rows
