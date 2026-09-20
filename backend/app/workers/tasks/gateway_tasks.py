from __future__ import annotations

import uuid

from app.core.async_runner import run_in_worker_loop
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.remediation_orchestrator import RemediationOrchestrator
from app.workers.celery_app import celery_app


async def _execute(action_id: str) -> dict:
    async with SessionLocal() as session:
        action = await RemediationOrchestrator(session).run(uuid.UUID(action_id))
        return {"action_id": str(action.id), "status": action.status.value}


@celery_app.task(bind=True, name="opspilot.execute_remediation", max_retries=get_settings().tool_max_retries)
def execute_remediation_task(self, action_id: str) -> dict:
    try:
        return run_in_worker_loop(_execute(action_id))
    except Exception as exc:
        if self.request.retries < get_settings().tool_max_retries:
            raise self.retry(exc=exc, countdown=min(30, 2 ** self.request.retries))
        return {"action_id": action_id, "status": "FAILED", "error": type(exc).__name__}
