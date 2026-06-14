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
