from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .ai import AIConfigError, AIServiceError
from .config import settings
from .routers import ai, applications, cvs, health, jobs

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AIConfigError)
def _ai_config_error(request: Request, exc: AIConfigError) -> JSONResponse:
    """AI layer not configured (e.g. missing API key) → 503, never a 500."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)}
    )


@app.exception_handler(AIServiceError)
def _ai_service_error(request: Request, exc: AIServiceError) -> JSONResponse:
    """An attempted Claude call failed upstream → 502 (the run is already logged)."""
    return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={"detail": str(exc)})


app.include_router(health.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(applications.router, prefix="/api")
app.include_router(cvs.router, prefix="/api")
app.include_router(ai.router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs"}
