from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.issues import router as issues_router
from backend.app.api.v1.projects import router as projects_router
from backend.app.api.v1.switch import router as switch_router
from backend.app.core.config import settings
from backend.app.core.logging import setup_logging
from backend.app.schemas.switch import SwitchAgentRegistration
from backend.app.services.switch_adapter import switch_adapter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT}]")

    # Register the ORCHESTRATOR agent identity with Switch on startup.
    # Best-effort: if Switch is unreachable the adapter degrades gracefully
    # and the backend continues normally. Canonical state lives in PostgreSQL.
    orchestrator = SwitchAgentRegistration(
        agent_id="pragmata-orchestrator",
        display_name="PRAGMATA Orchestrator",
        role="ORCHESTRATOR",
        capabilities=["state_management", "room_coordination", "task_dispatch"],
    )
    registered = await switch_adapter.register_agent(orchestrator)
    logger.info(
        f"Switch agent registration: {'OK' if registered else 'QUEUED'} "
        f"(connected={switch_adapter.is_connected})"
    )

    yield
    logger.info(f"Shutting down {settings.PROJECT_NAME}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# CORS Middleware
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )


# Routers
app.include_router(health_router, tags=["Health"])
app.include_router(health_router, prefix="/api/v1", tags=["Health"])
app.include_router(projects_router, prefix="/api/v1")
app.include_router(issues_router, prefix="/api/v1")
app.include_router(switch_router, prefix="/api/v1")
