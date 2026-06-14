from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    prefix: str
    options: dict | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None
    options: dict | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    prefix: str
    active: bool
    options: dict | None = None

    model_config = {"from_attributes": True}
