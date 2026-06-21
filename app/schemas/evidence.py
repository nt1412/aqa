import datetime as dt

from pydantic import BaseModel


class ArtifactOut(BaseModel):
    id: int
    execution_id: int
    artifact_type: str
    title: str | None = None
    blob_key: str
    size: int | None = None
    mime_type: str | None = None

    model_config = {"from_attributes": True}


class ClaimOut(BaseModel):
    id: int
    execution_id: int
    claim_text: str
    created_at: dt.datetime
    verification_count: int = 0

    model_config = {"from_attributes": True}


class ClaimWithVerdict(BaseModel):
    id: int
    execution_id: int
    claim_text: str
    created_at: dt.datetime
    verification_count: int = 0
    verdict: str | None = None  # latest verdict, or None if still unverified


class VerificationCreate(BaseModel):
    verdict: str  # confirmed|refuted|inconclusive
    reasoning: dict | None = None


class VerificationOut(BaseModel):
    id: int
    claim_id: int
    auditor_id: int
    verdict: str
    reasoning: dict | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class AuditReportCreate(BaseModel):
    entity_type: str  # case_version|suite|plan
    entity_id: int
    findings: dict | None = None
    quality_score: int | None = None


class AuditReportOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    auditor_id: int
    findings: dict | None = None
    quality_score: int | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class CaseEvaluation(BaseModel):
    case_version_id: int
    version: int
    summary: str | None = None
    step_count: int
    execution_count: int
    last_status: str | None = None


class EvidenceExecution(BaseModel):
    id: int
    status: str
    build_id: int | None = None
    created_at: dt.datetime
    claims: list[str] = []
    artifacts: list[ArtifactOut] = []

    model_config = {"from_attributes": True}


class EvidenceBundle(BaseModel):
    case_id: int
    executions: list[EvidenceExecution] = []


class AgentExecutionOut(BaseModel):
    id: int
    version_id: int
    status: str
    plan_id: int | None = None
    build_id: int | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class SimilarFailure(BaseModel):
    execution_id: int
    case_id: int
    status: str
    distance: float


class StepFailure(BaseModel):
    step_id: int
    status: str
    notes: str | None = None


class FailureExecution(BaseModel):
    execution_id: int
    status: str
    notes: str | None = None
    step_failures: list[StepFailure] = []


class RecurrenceHit(BaseModel):
    execution_id: int
    case_id: int
    status: str
    rank: float  # ts_rank_cd; higher = stronger keyword overlap


class FailureContext(BaseModel):
    case_id: int
    case_name: str
    recent_executions: list[FailureExecution] = []
    prior_reasoning: list[dict] = []
    # reasoning of the most-recent PASSING run for this case ("why it was last
    # green" — often the fix for the issue now recurring). Surfaced separately so
    # the recency cap on prior_reasoning can't bury it.
    last_green_reasoning: dict | None = None
    artifacts: list[ArtifactOut] = []
    similar_failures: list[SimilarFailure] = []
