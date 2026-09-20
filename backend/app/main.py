from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.events import router as events_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.simulator import router as simulator_router
from app.api.v1.investigations import router as investigations_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.remediation import router as remediation_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.policies import router as policies_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.core.logging import configure_logging
from app.core.redis import close_redis

settings = get_settings()
configure_logging(settings)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("opspilot_starting", extra={"environment": settings.environment})
    
    from app.core.database import SessionLocal, engine
    from app.simulator.manager import get_simulator_manager
    try:
        async with SessionLocal() as session:
            await get_simulator_manager().recover_stale_runs(session)
    except Exception as e:
        logger.error(f"Failed to recover stale runs: {e}")
        
    yield
    await close_redis()
    await engine.dispose()
    logger.info("opspilot_stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Incident intelligence and controlled remediation platform.",
    lifespan=lifespan,
)
app.add_exception_handler(AppError, app_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.include_router(health_router, prefix="/health")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(incidents_router, prefix="/api/v1")
app.include_router(simulator_router, prefix="/api/v1")
app.include_router(investigations_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(remediation_router, prefix="/api/v1")
app.include_router(approvals_router, prefix="/api/v1")
app.include_router(policies_router, prefix="/api/v1")


@app.get("/", tags=["system"], summary="OpsPilot service metadata")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "version": settings.app_version}
# trigger reload 2

