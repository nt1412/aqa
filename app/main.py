from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.errors import (
    Conflict,
    Forbidden,
    NotFound,
    Unauthorized,
    ValidationFailed,
)

_ERROR_STATUS = {
    NotFound: 404,
    Conflict: 409,
    Unauthorized: 401,
    Forbidden: 403,
    ValidationFailed: 422,
}


def create_app() -> FastAPI:
    from app.config import get_settings

    settings = get_settings()
    if settings.environment == "prod" and settings.jwt_secret == "change-me-in-production":
        raise RuntimeError("JWT_SECRET must be set when ENVIRONMENT=prod")

    app = FastAPI(title="AQA", version="0.1.0")

    @app.exception_handler(NotFound)
    @app.exception_handler(Conflict)
    @app.exception_handler(Unauthorized)
    @app.exception_handler(Forbidden)
    @app.exception_handler(ValidationFailed)
    async def _service_error_handler(request: Request, exc: Exception):
        status = _ERROR_STATUS.get(type(exc), 400)
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    from app.api import (
        assignments,
        auth,
        evidence,
        executions,
        plans,
        platforms,
        projects,
        requirements,
        suites,
        testcases,
        users,
    )

    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(suites.router)
    app.include_router(testcases.router)
    app.include_router(executions.router)
    app.include_router(platforms.router)
    app.include_router(plans.router)
    app.include_router(assignments.router)
    app.include_router(evidence.router)
    app.include_router(requirements.router)
    app.include_router(users.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
