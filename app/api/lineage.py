from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.services import lineage

router = APIRouter(prefix="/api/v1", tags=["lineage"])


@router.get("/plans/{plan_id}/build-timeline")
async def build_timeline(plan_id: int, session: SessionDep, user: CurrentUser):
    """Builds for a plan, newest first, each with its pass/fail/blocked/not_run rollup."""
    return await lineage.list_builds_enriched(session, plan_id)


@router.get("/builds/{build_id}")
async def build_detail(build_id: int, session: SessionDep, user: CurrentUser):
    """Build header + rollup + each case's latest result in the build."""
    return await lineage.build_detail(session, build_id)


@router.get("/cases/{case_id}/history")
async def case_history(case_id: int, session: SessionDep, user: CurrentUser):
    """A case's latest result per build, chronological, with broke/fixed transitions."""
    return await lineage.case_history(session, case_id)


@router.get("/builds/{build_id}/compare")
async def compare(build_id: int, session: SessionDep, user: CurrentUser, to: str = "baseline"):
    """Classify each case between this build and another build (?to=<id>) or its
    auto-resolved baseline (?to=baseline): regression / fixed / still_failing /
    still_passing / new_test / removed."""
    return await lineage.compare(session, build_id, to)
