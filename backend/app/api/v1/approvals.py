from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_roles
from app.core.database import get_db_session
from app.core.errors import AppError
from app.models.domain import Approval
from app.models.user import Role, User
from app.policies.approval_service import ApprovalService
from app.workers.tasks.gateway_tasks import execute_remediation_task

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=2000)


def _read(approval: Approval) -> dict:
    action = approval.remediation_action
    return {"id": str(approval.id), "remediation_action_id": str(approval.remediation_action_id),
            "status": approval.status.value, "requested_by": str(approval.requested_by),
            "approved_by": str(approval.approved_by) if approval.approved_by else None,
            "reason": approval.reason, "expires_at": approval.expires_at,
            "created_at": approval.created_at, "updated_at": approval.updated_at,
            "action_type": action.action_type if action else None, "risk_level": action.risk_level.value if action else None}


@router.get("/pending", summary="List pending approvals")
async def pending_approvals(_: User = Depends(require_roles(Role.ADMIN, Role.ENGINEER)),
                             session: AsyncSession = Depends(get_db_session)) -> dict:
    items = await ApprovalService(session).pending()
    return {"data": [_read(item) for item in items]}


async def _decide(approval_id: uuid.UUID, payload: ApprovalDecisionRequest, current_user: User,
                  session: AsyncSession, approve: bool) -> dict:
    approval = await ApprovalService(session).decide(approval_id, current_user, approve=approve, reason=payload.reason)
    task_id = None
    if approve:
        try:
            task_id = execute_remediation_task.apply_async(args=[str(approval.remediation_action_id)]).id
        except Exception as exc:
            raise AppError("REMEDIATION_QUEUE_UNAVAILABLE", "Approved remediation could not be queued", 503) from exc
    return {"data": {**_read(approval), "task_id": task_id}}


@router.post("/{approval_id}/approve", summary="Approve remediation")
async def approve(approval_id: uuid.UUID, payload: ApprovalDecisionRequest = ApprovalDecisionRequest(),
                  current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)) -> dict:
    return await _decide(approval_id, payload, current_user, session, True)


@router.post("/{approval_id}/reject", summary="Reject remediation")
async def reject(approval_id: uuid.UUID, payload: ApprovalDecisionRequest = ApprovalDecisionRequest(),
                 current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)) -> dict:
    return await _decide(approval_id, payload, current_user, session, False)
