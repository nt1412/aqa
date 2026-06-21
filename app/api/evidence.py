import base64
import binascii

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.schemas.evidence import (
    AgentExecutionOut,
    ArtifactOut,
    AuditReportCreate,
    AuditReportOut,
    CaseEvaluation,
    ClaimOut,
    ClaimWithVerdict,
    EvidenceBundle,
    FailureContext,
    RecurrenceHit,
    SimilarFailure,
    VerificationCreate,
    VerificationOut,
)
from app.services import evidence
from app.services.errors import ValidationFailed

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
    try:
        content = base64.b64decode(body.content, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValidationFailed("content must be valid base64") from e
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


@router.get("/claims", response_model=list[ClaimWithVerdict])
async def all_claims(
    session: SessionDep,
    user: CurrentUser,
    project_id: int | None = None,
    plan_id: int | None = None,
):
    """All claims with their latest verdict — the audit board's full state."""
    return await evidence.list_claims(session, project_id, plan_id)


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


@router.get("/cases/{case_id}/evidence", response_model=EvidenceBundle)
async def case_evidence(case_id: int, session: SessionDep, user: CurrentUser):
    return await evidence.get_execution_evidence(session, case_id)


@router.get("/agents/{agent_id}/executions", response_model=list[AgentExecutionOut])
async def agent_history(
    agent_id: int, session: SessionDep, user: CurrentUser, project_id: int | None = None
):
    return await evidence.get_agent_execution_history(session, agent_id, project_id)


@router.get("/cases/{case_id}/similar-failures", response_model=list[SimilarFailure])
async def similar_failures(case_id: int, session: SessionDep, user: CurrentUser, n: int = 5):
    return await evidence.search_similar_failures(session, case_id, n)


@router.get("/recurrences", response_model=list[RecurrenceHit])
async def recurrences(
    q: str,
    session: SessionDep,
    user: CurrentUser,
    project_id: int | None = None,
    n: int = 5,
):
    return await evidence.search_recurrences(session, q, project_id, n)


@router.get("/cases/{case_id}/failure-context", response_model=FailureContext)
async def failure_context(
    case_id: int,
    session: SessionDep,
    user: CurrentUser,
    plan_id: int | None = None,
    last_n: int = 5,
):
    return await evidence.get_failure_context(session, case_id, plan_id, last_n)
