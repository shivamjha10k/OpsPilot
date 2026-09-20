from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import InvestigationRead
from app.core.auth import get_current_user, require_roles
from app.core.database import get_db_session
from app.core.errors import AppError
from app.gateway.service import ToolGateway
from app.models.domain import AIInvestigation, Incident, RemediationAction, RemediationStatus
from app.models.user import Role, User
from app.workers.tasks.gateway_tasks import execute_remediation_task
from app.verification.engine import VerificationEngine

router = APIRouter(tags=["remediation"])


class RemediationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: str = Field(min_length=1, max_length=120)
    parameters: dict = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=255)


def _read_action(action: RemediationAction) -> dict:
    return {"id": str(action.id), "incident_id": str(action.incident_id), "action_type": action.action_type,
            "status": action.status.value, "risk_level": action.risk_level.value, "requested_by": str(action.requested_by) if action.requested_by else None,
            "approved_by": str(action.approved_by) if action.approved_by else None, "requested_at": action.requested_at,
            "executed_at": action.executed_at, "completed_at": action.completed_at, "result": action.result,
            "error": action.error, "idempotency_key": action.idempotency_key,
            "approval_id": str(action.approval.id) if action.approval else None,
            "policy_decision": action.policy_decision}


@router.get("/incidents/{incident_id}/remediation/recommendations", summary="Get remediation recommendations")
async def recommendations(incident_id: uuid.UUID, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)) -> dict:
    if await session.get(Incident, incident_id) is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident does not exist", 404)
    investigation = await session.scalar(select(AIInvestigation).where(AIInvestigation.incident_id == incident_id)
                                         .order_by(AIInvestigation.created_at.desc()))
    if investigation is None:
        return {"data": []}
    return {"data": [{"investigation_id": str(investigation.id), "action": investigation.recommendation_data or {},
                      "risk_level": investigation.risk_level.value, "confidence": investigation.confidence,
                      "knowledge_references": investigation.knowledge_references or []}]}


@router.post("/incidents/{incident_id}/remediation", status_code=202, summary="Request simulated remediation")
async def request_remediation(incident_id: uuid.UUID, payload: RemediationRequest,
                               current_user: User = Depends(require_roles(Role.ENGINEER, Role.ADMIN)),
                               session: AsyncSession = Depends(get_db_session)) -> dict:
    gateway = ToolGateway(session)
    action, created = await gateway.request(incident_id, payload.action_type, payload.parameters,
                                            payload.idempotency_key, current_user)
    if created and action.status is RemediationStatus.PENDING:
        try:
            task = execute_remediation_task.apply_async(args=[str(action.id)])
            return {"data": {**_read_action(action), "task_id": task.id}}
        except Exception as exc:
            action.status = RemediationStatus.FAILED
            action.error = "Remediation could not be queued"
            await session.commit()
            raise AppError("REMEDIATION_QUEUE_UNAVAILABLE", "Remediation could not be queued", 503) from exc
    return {"data": _read_action(action)}


@router.get("/remediation/{action_id}", summary="Get remediation status")
async def remediation_status(action_id: uuid.UUID, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)) -> dict:
    return {"data": _read_action(await ToolGateway(session).get_action(action_id))}


@router.get("/remediation/{action_id}/verification", summary="Get remediation verification")
async def remediation_verification(action_id: uuid.UUID, _: User = Depends(get_current_user),
                                   session: AsyncSession = Depends(get_db_session)) -> dict:
    action = await ToolGateway(session).get_action(action_id)
    result = (action.result or {}).get("verification", [])
    return {"data": {"remediation_action_id": str(action.id), "status": (action.result or {}).get("verification_status"),
                      "attempts": len(result), "verification": result}}
