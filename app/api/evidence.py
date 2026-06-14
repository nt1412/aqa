import base64

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.schemas.evidence import (
    ArtifactOut,
    AuditReportCreate,
    AuditReportOut,
    CaseEvaluation,
    ClaimOut,
    VerificationCreate,
    VerificationOut,
)
from app.services import evidence

router = APIRouter(prefix="/api/v1", tags=["evidence"])


class _ArtifactIn(BaseModel):
    artifact_type: str
    title: str | None = None
    content: str  # base64-encoded bytes
    mime_type: str | None = None


@router.post(
    "/executions/{execution_id}/artifacts",
    response_model=ArtifactOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_artifact(
    execution_id: int, body: _ArtifactIn, session: SessionDep, user: CurrentUser
):
    content = base64.b64decode(body.content)
    return await evidence.upload_artifact(
        session, execution_id, body.artifact_type, body.title, content, body.mime_type
    )


@router.get("/executions/{execution_id}/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(execution_id: int, session: SessionDep, user: CurrentUser):
    return await evidence.list_artifacts(session, execution_id)


@router.get("/claims/unverified", response_model=list[ClaimOut])
async def unverified_claims(
    session: SessionDep,
    user: CurrentUser,
    project_id: int | None = None,
    plan_id: int | None = None,
):
    return await evidence.list_unverified_claims(session, project_id, plan_id)


@router.post(
    "/claims/{claim_id}/verify",
    response_model=VerificationOut,
    status_code=status.HTTP_201_CREATED,
)
async def verify(claim_id: int, body: VerificationCreate, session: SessionDep, user: CurrentUser):
    return await evidence.verify_claim(session, claim_id, body, auditor_id=user.id)


@router.post("/audit-reports", response_model=AuditReportOut, status_code=status.HTTP_201_CREATED)
async def create_audit_report(body: AuditReportCreate, session: SessionDep, user: CurrentUser):
    return await evidence.create_audit_report(session, body, auditor_id=user.id)


@router.get("/case-versions/{case_version_id}/evaluation", response_model=CaseEvaluation)
async def evaluate(case_version_id: int, session: SessionDep, user: CurrentUser):
    return await evidence.evaluate_test_case(session, case_version_id)
