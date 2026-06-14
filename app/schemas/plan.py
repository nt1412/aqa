import datetime as dt

from pydantic import BaseModel


class PlanCreate(BaseModel):
    name: str
    notes: str | None = None


class PlanUpdate(BaseModel):
    name: str | None = None
    notes: str | None = None
    active: bool | None = None
    is_open: bool | None = None


class PlanOut(BaseModel):
    id: int
    project_id: int
    name: str
    notes: str | None = None
    active: bool
    is_open: bool

    model_config = {"from_attributes": True}


class PlanCaseAdd(BaseModel):
    case_ids: list[int]
    platform_id: int | None = None
    urgency: int = 2


class PlanCaseOut(BaseModel):
    id: int
    plan_id: int
    version_id: int
    platform_id: int | None
    urgency: int

    model_config = {"from_attributes": True}


class RunManifestEntry(BaseModel):
    order: int
    urgency: int
    case_id: int
    external_id: str | None = None
    name: str | None = None
    importance: int | None = None
    latest_status: str
    depends_on: list[int] = []
    blocked_by: list[int] = []
    runnable: bool


class BuildCreate(BaseModel):
    name: str
    notes: str | None = None
    tag: str | None = None
    branch: str | None = None
    commit_id: str | None = None


class BuildOut(BaseModel):
    id: int
    plan_id: int
    name: str
    notes: str | None = None
    tag: str | None = None
    branch: str | None = None
    commit_id: str | None = None
    active: bool

    model_config = {"from_attributes": True}


class MilestoneCreate(BaseModel):
    name: str
    target_date: dt.datetime | None = None
    start_date: dt.datetime | None = None


class MilestoneOut(BaseModel):
    id: int
    plan_id: int
    name: str
    target_date: dt.datetime | None = None
    start_date: dt.datetime | None = None

    model_config = {"from_attributes": True}
