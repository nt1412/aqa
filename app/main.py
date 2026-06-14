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
    app = FastAPI(title="AgentQA", version="0.1.0")

    @app.exception_handler(NotFound)
    @app.exception_handler(Conflict)
    @app.exception_handler(Unauthorized)
    @app.exception_handler(Forbidden)
    @app.exception_handler(ValidationFailed)
    async def _service_error_handler(request: Request, exc: Exception):
        status = _ERROR_STATUS.get(type(exc), 400)
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    from app.api import auth, projects

    app.include_router(auth.router)
    app.include_router(projects.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
