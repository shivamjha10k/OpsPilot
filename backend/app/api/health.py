import logging
import asyncio

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.database import check_database
from app.core.redis import check_redis
from app.workers.celery_app import celery_app
from app.core.config import get_settings
from app.rag.qdrant_repository import QdrantRepository

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/live", summary="Check whether the API process is alive")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Check whether required dependencies are available")
async def readiness() -> JSONResponse:
    checks: dict[str, str] = {}
    healthy = True

    for name, check in (("database", check_database), ("redis", check_redis)):
        try:
            await check()
            checks[name] = "ok"
        except Exception:
            logger.exception("readiness_check_failed", extra={"dependency": name})
            checks[name] = "unavailable"
            healthy = False

    payload = {"status": "ok" if healthy else "not_ready", "checks": checks}
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )


@router.get("/worker", summary="Check whether a Celery worker responds")
async def worker_health() -> JSONResponse:
    def ping_worker() -> dict | None:
        return celery_app.control.inspect(timeout=0.5).ping()

    try:
        replies = await asyncio.to_thread(ping_worker)
        workers = sorted((replies or {}).keys())
        payload = {"status": "ok" if workers else "unavailable", "workers": workers}
        return JSONResponse(status_code=200 if workers else 503, content=payload)
    except Exception:
        logger.exception("worker_health_check_failed")
        return JSONResponse(status_code=503, content={"status": "unavailable", "workers": []})


@router.get("/qdrant", summary="Check whether Qdrant responds")
async def qdrant_health() -> JSONResponse:
    available = await QdrantRepository(get_settings()).health()
    return JSONResponse(status_code=200 if available else 503,
                        content={"status": "ok" if available else "unavailable"})
