from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import InvestigationRead
from app.ai.service import AIInvestigationService
from app.core.auth import get_current_user, require_roles
from app.core.database import get_db_session
from app.core.errors import AppError
from app.models.domain import InvestigationStatus
from app.models.user import Role, User
from app.workers.tasks.investigation_tasks import investigate_incident_task

router = APIRouter(tags=["investigations"])


def _read(item) -> dict:
    return InvestigationRead(
        id=str(item.id), incident_id=str(item.incident_id), model=item.model, summary=item.summary,
        root_cause=item.root_cause, confidence=item.confidence, evidence=item.evidence or {},
        recommendation=item.recommendation, recommendation_data=item.recommendation_data or {},
        observations=item.observations or [], probable_root_causes=item.probable_root_causes or [],
        knowledge_references=item.knowledge_references or [],
        risk_level=item.risk_level.value, requires_approval=item.requires_approval, status=item.status.value,
        prompt_version=item.prompt_version, duration_ms=item.duration_ms, error_code=item.error_code,
        task_id=item.task_id, created_at=item.created_at, updated_at=item.updated_at,
        started_at=item.started_at, completed_at=item.completed_at,
    ).model_dump(mode="json")


@router.post("/incidents/{incident_id}/investigate", status_code=202, summary="Queue an incident investigation")
async def request_investigation(
    incident_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_roles(Role.ENGINEER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = AIInvestigationService(session)
    item, created = await service.request_investigation(incident_id, current_user.id)
    if not created:
        return {"data": {"investigation_id": str(item.id), "incident_id": str(incident_id), "status": item.status.value,
                          "task_id": item.task_id}}
    try:
        task = investigate_incident_task.apply_async(args=[str(incident_id), str(item.id)])
        await service.attach_task(item.id, task.id)
    except Exception as exc:
        item.error_code = "AI_QUEUE_UNAVAILABLE"
        item.status = InvestigationStatus.FAILED
        await session.commit()
        raise AppError("AI_QUEUE_UNAVAILABLE", "Investigation could not be queued", 503) from exc
    return {"data": {"investigation_id": str(item.id), "incident_id": str(incident_id), "status": "PENDING", "task_id": task.id}}


@router.get("/investigations/{investigation_id}", summary="Get an investigation")
async def get_investigation(
    investigation_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    item = await AIInvestigationService(session).get(investigation_id)
    return {"data": _read(item)}
