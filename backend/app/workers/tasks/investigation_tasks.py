from __future__ import annotations

import logging
import uuid

from celery.exceptions import SoftTimeLimitExceeded

from app.core.database import SessionLocal
from app.core.async_runner import run_in_worker_loop
from app.core.config import get_settings
from app.models.domain import InvestigationStatus
from app.ai.service import AIInvestigationService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _run(incident_id: str, investigation_id: str | None, current_task_id: str | None):
    async with SessionLocal() as session:
        investigation = await AIInvestigationService(session).investigate_incident(
            uuid.UUID(incident_id),
            uuid.UUID(investigation_id) if investigation_id else None,
            current_task_id=current_task_id
        )
        if investigation.status == InvestigationStatus.COMPLETED and investigation.recommendation_data:
            from app.models.domain import Incident, IncidentStatus, RemediationStatus
            from app.services.incident_engine import IncidentStateMachine
            from app.gateway.service import ToolGateway
            from app.models.user import User, Role
            from app.workers.tasks.gateway_tasks import execute_remediation_task
            from sqlalchemy import select
            
            incident = await session.scalar(select(Incident).where(Incident.id == investigation.incident_id).with_for_update())
            if incident and incident.status == IncidentStatus.DETECTED:
                IncidentStateMachine.transition(incident, IncidentStatus.ACKNOWLEDGED)
                IncidentStateMachine.transition(incident, IncidentStatus.INVESTIGATING)
                IncidentStateMachine.transition(incident, IncidentStatus.DIAGNOSED)
                await session.commit()
                await session.refresh(incident)
            
            action_type = investigation.recommendation_data.get("type")
            parameters = investigation.recommendation_data.get("parameters", {})
            
            if action_type and incident.status == IncidentStatus.DIAGNOSED:
                actor = None
                if investigation.requested_by:
                    actor = await session.get(User, investigation.requested_by)
                if not actor:
                    actor = await session.scalar(select(User).where(User.role == Role.ADMIN).limit(1))
                
                if actor:
                    try:
                        gateway = ToolGateway(session)
                        idempotency_key = f"inv-{investigation.id}-{action_type}"
                        action, _ = await gateway.request(
                            incident_id=incident.id,
                            action_type=action_type,
                            parameters=parameters,
                            idempotency_key=idempotency_key,
                            actor=actor
                        )
                        if action.status == RemediationStatus.PENDING:
                            IncidentStateMachine.transition(incident, IncidentStatus.REMEDIATION_PENDING)
                            await session.commit()
                            execute_remediation_task.apply_async(args=[str(action.id)])
                        elif action.status == RemediationStatus.APPROVAL_REQUIRED:
                            IncidentStateMachine.transition(incident, IncidentStatus.REMEDIATION_PENDING)
                            IncidentStateMachine.transition(incident, IncidentStatus.APPROVAL_PENDING)
                            await session.commit()
                    except Exception as e:
                        logger.error(f"Auto-remediation request failed: {e}")
        return investigation


@celery_app.task(bind=True, name="opspilot.investigate_incident", acks_late=True)
def investigate_incident_task(self, incident_id: str, investigation_id: str | None = None) -> dict:
    try:
        incident_uuid = uuid.UUID(incident_id)
        investigation_uuid = uuid.UUID(investigation_id) if investigation_id else None
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("invalid investigation identifiers") from exc
    try:
        item = run_in_worker_loop(_run(str(incident_uuid), str(investigation_uuid) if investigation_uuid else None, self.request.id))
        if item.status is InvestigationStatus.FAILED and item.error_code in {
            "AI_PROVIDER_TIMEOUT", "AI_PROVIDER_UNAVAILABLE", "AI_INVESTIGATION_TIMEOUT"
        } and self.request.retries < get_settings().ai_max_retries:
            raise self.retry(countdown=min(60, 2 ** self.request.retries))
        return {"investigation_id": str(item.id), "incident_id": str(item.incident_id), "status": item.status.value}
    except SoftTimeLimitExceeded:
        logger.error("investigation_task_timeout", extra={"incident_id": incident_id})
        raise
    except Exception:
        logger.exception("investigation_task_failed", extra={"incident_id": incident_id})
        raise
