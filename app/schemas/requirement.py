from pydantic import BaseModel


class ReqSpecCreate(BaseModel):
    doc_id: str
    name: str
    scope: str | None = None


class ReqSpecOut(BaseModel):
    id: int
    project_id: int
    doc_id: str
    name: str
    scope: str | None = None

    model_config = {"from_attributes": True}


class RequirementCreate(BaseModel):
    req_doc_id: str
    name: str
    scope: str | None = None
    link_to_cases: list[int] = []


class ReqVersionOut(BaseModel):
    id: int
    req_id: int
    version: int
    scope: str | None = None
    status: str | None = None

    model_config = {"from_attributes": True}


class RequirementOut(BaseModel):
    id: int
    spec_id: int
    req_doc_id: str
    name: str
    current_version: ReqVersionOut | None = None

    model_config = {"from_attributes": True}


class CoverageLink(BaseModel):
    case_ids: list[int]


class CoverageGap(BaseModel):
    requirement_id: int
    req_version_id: int
    req_doc_id: str
    name: str


class TraceabilityRow(BaseModel):
    requirement_id: int
    req_doc_id: str
    name: str
    covered_case_ids: list[int] = []
