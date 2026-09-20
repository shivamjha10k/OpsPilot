from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.core.errors import AppError
from app.gateway.registry import build_tool_registry
from app.models.domain import (
    Approval, ApprovalStatus, AuditLog, Incident, IncidentStatus, RemediationAction, RemediationStatus,
)
from app.models.user import Role, User

from .binding import action_fingerprint
from .engine import PolicyEngine
from .schemas import PolicyDecision


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.registry = build_tool_registry()
        self.engine = PolicyEngine()

    async def pending(self) -> list[Approval]:
        result = await self.session.scalars(
            select(Approval).options(joinedload(Approval.remediation_action)).where(Approval.status == ApprovalStatus.PENDING)
            .order_by(Approval.created_at.asc())
        )
        approvals = list(result.all())
        now = datetime.now(timezone.utc)
        changed = False
        for approval in approvals:
            if approval.expires_at <= now:
                approval.status = ApprovalStatus.EXPIRED
                approval.remediation_action.status = RemediationStatus.REJECTED
                self.session.add(AuditLog(actor_id=None, action="APPROVAL_EXPIRED", resource_type="Approval",
                                          resource_id=str(approval.id), result="SUCCESS",
                                          metadata_json={"remediation_action_id": str(approval.remediation_action_id)}))
                changed = True
        if changed:
            await self.session.commit()
        return [item for item in approvals if item.status is ApprovalStatus.PENDING]

    async def decide(self, approval_id: uuid.UUID, actor: User, *, approve: bool, reason: str | None = None) -> Approval:
        approval = await self.session.scalar(
            select(Approval).options(joinedload(Approval.remediation_action), joinedload(Approval.requester))
            .where(Approval.id == approval_id).with_for_update()
        )
        if approval is None:
            raise AppError("APPROVAL_NOT_FOUND", "Approval does not exist", 404)
        action = approval.remediation_action
        now = datetime.now(timezone.utc)
        if approval.status is not ApprovalStatus.PENDING:
            raise AppError("APPROVAL_NOT_PENDING", "Approval is no longer pending", 409)
        if approval.expires_at <= now:
            approval.status = ApprovalStatus.EXPIRED
            action.status = RemediationStatus.REJECTED
            self.session.add(AuditLog(actor_id=actor.id, action="APPROVAL_EXPIRED", resource_type="Approval",
                                      resource_id=str(approval.id), result="SUCCESS",
                                      metadata_json={"remediation_action_id": str(action.id)}))
            await self.session.commit()
            raise AppError("APPROVAL_EXPIRED", "Approval has expired", 409)
        if actor.role not in {Role.ENGINEER, Role.ADMIN}:
            self._audit(actor, approval, "UNAUTHORIZED_APPROVAL_ATTEMPT", "FAILURE")
            await self.session.commit()
            raise AppError("INSUFFICIENT_PERMISSIONS", "You cannot approve remediation", 403)
        if approve and actor.id == approval.requested_by and action.risk_level.value in {"HIGH", "CRITICAL"}:
            self._audit(actor, approval, "SELF_APPROVAL_ATTEMPT", "FAILURE")
            await self.session.commit()
            raise AppError("SELF_APPROVAL_FORBIDDEN", "The requester cannot approve this action", 403)
        incident = await self.session.scalar(select(Incident).where(Incident.id == action.incident_id).with_for_update())
        if incident is None or incident.service is None:
            raise AppError("INCIDENT_NOT_FOUND", "Incident does not exist", 404)
        if incident.status in {IncidentStatus.RESOLVED, IncidentStatus.ESCALATED, IncidentStatus.FAILED}:
            self._audit(actor, approval, "APPROVAL_ACTION_NOT_PERMITTED", "FAILURE")
            await self.session.commit()
            raise AppError("INCIDENT_NOT_ACTIONABLE", "The incident no longer permits remediation", 409)
        current = await self.engine.evaluate_action(
            self.session, action_type=action.action_type, environment=incident.service.environment,
            risk_level=action.risk_level, actor=approval.requester, parameters=action.parameters,
            registry=self.registry, incident_id=action.incident_id, lock_policies=True,
        )
        current_fingerprint = action_fingerprint(
            incident_id=action.incident_id, action_type=action.action_type, parameters=action.parameters,
            environment=incident.service.environment, risk_level=action.risk_level,
            policy_id=current.matched_policy_id, policy_version=current.policy_version,
        )
        if action.action_fingerprint != current_fingerprint:
            self._audit(actor, approval, "INVALID_APPROVAL_ACTION_MISMATCH", "FAILURE")
            await self.session.commit()
            raise AppError("APPROVAL_ACTION_MISMATCH", "The action or policy changed after approval", 409)
        if current.decision is not PolicyDecision.REQUIRE_APPROVAL:
            self._audit(actor, approval, "POLICY_CHANGE_APPROVAL_INVALIDATED", "FAILURE", current.reason)
            await self.session.commit()
            raise AppError("APPROVAL_POLICY_CHANGED", "Current policy no longer requires this approval", 409)
        if current.decision is PolicyDecision.DENY:
            self._audit(actor, approval, "POLICY_CHANGE_EXECUTION_BLOCKED", "FAILURE", current.reason)
            await self.session.commit()
            raise AppError("POLICY_DENIED", "Current policy denies this action", 403)
        if approve:
            approval.status = ApprovalStatus.APPROVED
            approval.approved_by = actor.id
            approval.reason = reason
            action.approved_by = actor.id
            action.status = RemediationStatus.APPROVED
            event = "APPROVAL_APPROVED"
        else:
            approval.status = ApprovalStatus.REJECTED
            approval.approved_by = actor.id
            approval.reason = reason
            action.approved_by = actor.id
            action.status = RemediationStatus.REJECTED
            event = "APPROVAL_REJECTED"
        self._audit(actor, approval, event, "SUCCESS", reason)
        await self.session.commit()
        return approval

    def _audit(self, actor: User, approval: Approval, event: str, result: str, reason: str | None = None) -> None:
        self.session.add(AuditLog(actor_id=actor.id, action=event, resource_type="Approval",
                                  resource_id=str(approval.id), result=result,
                                  metadata_json={"remediation_action_id": str(approval.remediation_action_id),
                                                 "reason": reason} if reason else
                                  {"remediation_action_id": str(approval.remediation_action_id)}))
