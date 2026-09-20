from __future__ import annotations

import uuid
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import AppError
from app.gateway.registry import build_tool_registry
from app.gateway.service import ToolGateway
from app.models.domain import ApprovalStatus, AuditLog, Incident, IncidentStatus, RemediationAction, RemediationStatus
from app.services.incident_engine import IncidentStateMachine
from app.verification.engine import VerificationEngine


class RemediationOrchestrator:
    """Coordinates gateway execution and bounded verification without mutating simulator state directly."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def run(self, action_id: uuid.UUID):
        action = await self.session.scalar(
            select(RemediationAction).where(RemediationAction.id == action_id)
            .options(selectinload(RemediationAction.incident))
            .with_for_update()
        )
        if action is None:
            raise AppError("REMEDIATION_NOT_FOUND", "Remediation action does not exist", 404)
        if action.status in {RemediationStatus.REJECTED, RemediationStatus.CANCELLED}:
            return action
        self.session.add(AuditLog(actor_id=None, action="REMEDIATION_EXECUTION_STARTED", resource_type="RemediationAction",
                                  resource_id=str(action.id), result="STARTED", metadata_json={"incident_id": str(action.incident_id)}))
        await self.session.commit()
        action = await self._execute_with_retries(action)
        if action.status is not RemediationStatus.COMPLETED:
            await self._failure(action, "REMEDIATION_EXECUTION_FAILED")
            await self.session.refresh(action)
            return action
        incident = await self.session.scalar(
            select(Incident)
            .where(Incident.id == action.incident_id)
            .options(selectinload(Incident.alerts), selectinload(Incident.service))
            .with_for_update()
        )
        if incident is None:
            raise AppError("INCIDENT_NOT_FOUND", "Incident does not exist", 404)
        self._advance_to_verifying(incident)
        action.result = {**(action.result or {}), "execution_status": "SUCCEEDED", "verification_status": "PENDING"}
        self.session.add(AuditLog(actor_id=None, action="VERIFICATION_STARTED", resource_type="RemediationAction",
                                  resource_id=str(action.id), result="STARTED", metadata_json={"incident_id": str(incident.id)}))
        await self.session.commit()
        criteria = VerificationEngine.criteria_for(incident).model_copy(
            update={"consecutive_successes": self.settings.verification_consecutive_successes}
        )
        verifier = VerificationEngine(self.session)
        latest = None
        for attempt in range(self.settings.verification_max_attempts):
            latest = await verifier.verify_remediation(action.id, criteria)
            if latest.status.value == "RECOVERED":
                await self.session.refresh(action)
                return action
            if attempt + 1 < self.settings.verification_max_attempts:
                await asyncio.sleep(self.settings.verification_interval_seconds)
        await self._escalate_after_verification(action.id)
        await self.session.refresh(action)
        return action

    async def _execute_with_retries(self, action: RemediationAction) -> RemediationAction:
        gateway = ToolGateway(self.session)
        for attempt in range(self.settings.tool_max_retries + 1):
            action = await gateway.execute_action(action.id)
            if action.status is RemediationStatus.COMPLETED:
                return action
            retryable = bool((action.result or {}).get("retryable"))
            tool = build_tool_registry().get(action.action_type)
            if not retryable or not tool.idempotent or attempt >= self.settings.tool_max_retries:
                return action
            approval = action.approval
            action.status = RemediationStatus.APPROVED if approval is not None and approval.status is ApprovalStatus.APPROVED else RemediationStatus.PENDING
            action.result = {**(action.result or {}), "retry_attempt": attempt + 1}
            self.session.add(AuditLog(
                actor_id=None, action="REMEDIATION_RETRY_ATTEMPTED", resource_type="RemediationAction",
                resource_id=str(action.id), result="RETRY",
                metadata_json={"attempt": attempt + 1, "max_retries": self.settings.tool_max_retries},
            ))
            await self.session.commit()
        return action

    @staticmethod
    def _advance_to_verifying(incident: Incident) -> None:
        if incident.status is IncidentStatus.DIAGNOSED:
            IncidentStateMachine.transition(incident, IncidentStatus.REMEDIATION_PENDING)
        if incident.status is IncidentStatus.REMEDIATION_PENDING:
            IncidentStateMachine.transition(incident, IncidentStatus.APPROVAL_PENDING)
        if incident.status is IncidentStatus.APPROVAL_PENDING:
            IncidentStateMachine.transition(incident, IncidentStatus.EXECUTING)
        if incident.status is IncidentStatus.EXECUTING:
            IncidentStateMachine.transition(incident, IncidentStatus.VERIFYING)

    async def _escalate_after_verification(self, action_id: uuid.UUID) -> None:
        action = await self.session.scalar(select(RemediationAction).where(RemediationAction.id == action_id))
        if action is None:
            return
        incident = await self.session.scalar(select(Incident).where(Incident.id == action.incident_id).with_for_update())
        if incident is not None:
            if incident.status is IncidentStatus.VERIFYING:
                IncidentStateMachine.transition(incident, IncidentStatus.FAILED)
            if incident.status is IncidentStatus.FAILED:
                IncidentStateMachine.transition(incident, IncidentStatus.ESCALATED)
        action.result = {**(action.result or {}), "verification_status": "ESCALATED"}
        self.session.add(AuditLog(actor_id=None, action="INCIDENT_ESCALATED", resource_type="Incident",
                                  resource_id=str(action.incident_id), result="FAILURE",
                                  metadata_json={"remediation_action_id": str(action.id), "reason": "verification_attempts_exhausted"}))
        await self.session.commit()

    async def _failure(self, action: RemediationAction, reason: str) -> None:
        action.error = reason
        action.result = {**(action.result or {}), "execution_status": "FAILED", "retryable": False}
        incident = await self.session.scalar(select(Incident).where(Incident.id == action.incident_id).with_for_update())
        if incident is not None:
            if incident.status is IncidentStatus.EXECUTING:
                IncidentStateMachine.transition(incident, IncidentStatus.FAILED)
            if incident.status is IncidentStatus.FAILED:
                IncidentStateMachine.transition(incident, IncidentStatus.ESCALATED)
        self.session.add(AuditLog(actor_id=None, action="REMEDIATION_ESCALATED", resource_type="Incident",
                                  resource_id=str(action.incident_id), result="FAILURE", metadata_json={"remediation_action_id": str(action.id), "reason": reason}))
        await self.session.commit()