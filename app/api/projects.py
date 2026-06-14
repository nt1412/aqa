from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.services import projects

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create(body: ProjectCreate, session: SessionDep, user: CurrentUser):
    return await projects.create_project(session, body)


@router.get("", response_model=list[ProjectOut])
async def list_all(session: SessionDep, user: CurrentUser, active: bool | None = None):
    return await projects.list_projects(session, active)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_one(project_id: int, session: SessionDep, user: CurrentUser):
    return await projects.get_project(session, project_id)


@router.put("/{project_id}", response_model=ProjectOut)
async def update(project_id: int, body: ProjectUpdate, session: SessionDep, user: CurrentUser):
    return await projects.update_project(session, project_id, body)
