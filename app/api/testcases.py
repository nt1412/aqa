from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.testcase import (
    DependencyCreate,
    DependencyOut,
    TestCaseCreate,
    TestCaseOut,
    VersionCreate,
    VersionOut,
)
from app.services import testcases

router = APIRouter(prefix="/api/v1", tags=["testcases"])


@router.post(
    "/suites/{suite_id}/cases", response_model=TestCaseOut, status_code=status.HTTP_201_CREATED
)
async def create(suite_id: int, body: TestCaseCreate, session: SessionDep, user: CurrentUser):
    tc = await testcases.create_test_case(session, suite_id, body)
    return await testcases.get_test_case(session, tc.id)


@router.get("/suites/{suite_id}/cases", response_model=list[TestCaseOut])
async def list_in_suite(suite_id: int, session: SessionDep, user: CurrentUser):
    return await testcases.list_cases_in_suite(session, suite_id)


@router.get("/cases/{case_id}", response_model=TestCaseOut)
async def get_one(case_id: int, session: SessionDep, user: CurrentUser):
    return await testcases.get_test_case(session, case_id)


@router.post("/cases/{case_id}/versions", response_model=VersionOut)
async def new_version(case_id: int, body: VersionCreate, session: SessionDep, user: CurrentUser):
    return await testcases.create_version(session, case_id, body)


@router.post(
    "/cases/{case_id}/dependencies",
    response_model=DependencyOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_dependency(
    case_id: int, body: DependencyCreate, session: SessionDep, user: CurrentUser
):
    """Record that this case depends on another (a prerequisite for run gating)."""
    rel = await testcases.add_dependency(session, case_id, body.depends_on_case_id)
    return DependencyOut(case_id=rel.source_id, depends_on_case_id=rel.dest_id)
