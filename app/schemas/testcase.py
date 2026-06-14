from pydantic import BaseModel


class StepIn(BaseModel):
    action: str
    expected_result: str | None = None
    execution_type: str = "manual"


class StepOut(StepIn):
    id: int
    step_number: int

    model_config = {"from_attributes": True}


class TestCaseCreate(BaseModel):
    name: str
    summary: str | None = None
    preconditions: str | None = None
    importance: int = 2
    execution_type: str = "manual"
    estimated_duration: int | None = None
    steps: list[StepIn] = []


class VersionOut(BaseModel):
    id: int
    version: int
    summary: str | None = None
    preconditions: str | None = None
    importance: int
    execution_type: str
    status: str
    active: bool
    steps: list[StepOut] = []

    model_config = {"from_attributes": True}


class TestCaseOut(BaseModel):
    id: int
    project_id: int
    suite_id: int
    external_id: str
    name: str
    current_version: VersionOut | None = None

    model_config = {"from_attributes": True}


class VersionCreate(BaseModel):
    summary: str | None = None
    preconditions: str | None = None
    importance: int | None = None
    execution_type: str | None = None
    steps: list[StepIn] | None = None


class DependencyCreate(BaseModel):
    depends_on_case_id: int


class DependencyOut(BaseModel):
    case_id: int
    depends_on_case_id: int
