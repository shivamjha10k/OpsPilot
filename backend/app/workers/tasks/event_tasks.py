from __future__ import annotations

import logging
import random
import time

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.config import get_settings
from app.core.async_runner import run_in_worker_loop
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.services.incident_engine import IncidentEngine
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

from app.workers.tasks.investigation_tasks import investigate_incident_task

async def _process(event_id: str, request_id: str | None) -> dict:
    async with SessionLocal() as session:
        engine = IncidentEngine(session)
        result = await engine.process_event(event_id, request_id=request_id)
        if result.incident:
            await engine.dispatch_pending_investigations(result.incident.id)
        return {"event_id": event_id, "status": "SUCCESS", "duplicate": result.duplicate}


async def _mark_failed(event_id: str, error: str) -> None:
    async with SessionLocal() as session:
        await IncidentEngine(session).mark_queue_failed(event_id, error)


@celery_app.task(bind=True, name="opspilot.process_event", acks_late=True)
def process_event_task(self, event_id: str, request_id: str | None = None) -> dict:
    if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 255:
        raise ValueError("event_id must be a non-empty string of at most 255 characters")
    settings = get_settings()
    started = time.monotonic()
    attempt = self.request.retries + 1
    logger.info("event_task_started", extra={"task_id": self.request.id, "event_id": event_id,
                                              "task_name": self.name, "attempt": attempt})
    try:
        result = run_in_worker_loop(_process(event_id, request_id))
        logger.info("event_task_completed", extra={"task_id": self.request.id, "event_id": event_id,
                                                    "duration_ms": int((time.monotonic() - started) * 1000)})
        return result
    except AppError as exc:
        logger.error("event_task_failed_domain", extra={"task_id": self.request.id, "event_id": event_id,
                                                         "error_type": exc.code})
        return {"event_id": event_id, "status": "FAILED", "error_code": exc.code}
    except SoftTimeLimitExceeded as exc:
        error = "event task soft time limit exceeded"
        if self.request.retries >= settings.celery_task_max_retries:
            run_in_worker_loop(_mark_failed(event_id, error))
            return {"event_id": event_id, "status": "FAILED", "error": error}
        raise self.retry(exc=exc, countdown=_backoff(self.request.retries))
    except (OperationalError, DBAPIError, ConnectionError) as exc:
        if self.request.retries >= settings.celery_task_max_retries:
            run_in_worker_loop(_mark_failed(event_id, str(exc)))
            return {"event_id": event_id, "status": "FAILED", "error": "database unavailable"}
        raise self.retry(exc=exc, countdown=_backoff(self.request.retries))
    except Exception as exc:
        if self.request.retries >= settings.celery_task_max_retries:
            run_in_worker_loop(_mark_failed(event_id, str(exc)))
            return {"event_id": event_id, "status": "FAILED", "error": "processing failed"}
        raise self.retry(exc=exc, countdown=_backoff(self.request.retries))


def _backoff(retries: int) -> int:
    return min(60, max(1, 2 ** retries) + random.randint(0, 2))
