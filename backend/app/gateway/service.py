from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import AppError
from app.gateway.registry import ToolRegistry, build_tool_registry
from app.gateway.schemas import ToolExecutionResult, ToolFailureResult
from app.models.domain import Approval, ApprovalStatus, AuditLog, Incident, IncidentStatus, RemediationAction, RemediationStatus
from app.models.user import User
from app.policies.binding import action_fingerprint
from app.policies.engine import PolicyEngine
from app.policies.schemas import PolicyDecision
from app.simulator.manager import get_simulator_manager

logger = logging.getLogger(__name__)


class ToolGateway:
    """The only application boundary capable of invoking simulator tools."""

    def __init__(self, session: AsyncSession, registry: ToolRegistry | None = None,
                 policy_engine: PolicyEngine | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        self.registry = registry or build_tool_registry(get_simulator_manager())
        self.policy_engine = policy_engine or PolicyEngine()

    async def request(self, incident_id: uuid.UUID, action_type: str, parameters: dict,
                      idempotency_key: str, actor: User) -> tuple[RemediationAction, bool]:
        if not idempotency_key or len(idempotency_key) > 255:
            raise AppError("INVALID_IDEMPOTENCY_KEY", "idempotency_key must be non-empty and at most 255 characters", 422)
        try:
            tool = self.registry.get(action_type)
        except KeyError as exc:
            raise AppError("UNKNOWN_TOOL", "Requested remediation tool is not registered", 422) from exc
        if actor.role not in tool.required_roles:
            raise AppError("INSUFFICIENT_PERMISSIONS", "You cannot execute this tool", 403)
        try:
            validated = tool.input_model.model_validate(parameters)
        except Exception as exc:
            raise AppError("INVALID_TOOL_PARAMETERS", "Tool parameters are invalid", 422) from exc
        if hasattr(validated, "desired_replicas") and validated.desired_replicas > self.settings.max_simulated_replicas:
            raise AppError("SIMULATOR_LIMIT_EXCEEDED", "desired_replicas exceeds the simulator limit", 422)
        if hasattr(validated, "desired_workers") and validated.desired_workers > self.settings.max_simulated_workers:
            raise AppError("SIMULATOR_LIMIT_EXCEEDED", "desired_workers exceeds the simulator limit", 422)
        incident = await self.session.scalar(select(Incident).where(Incident.id == incident_id).options(selectinload(Incident.service)))
        if incident is None:
            raise AppError("INCIDENT_NOT_FOUND", "Incident does not exist", 404)
        environment = incident.service.environment
        normalized_parameters = validated.model_dump(mode="json")
        decision = await self.policy_engine.evaluate_action(
            self.session, action_type=tool.name, environment=environment, risk_level=tool.risk_level,
            actor=actor, parameters=normalized_parameters, registry=self.registry,
            incident_id=incident_id, lock_policies=True,
        )
        fingerprint = action_fingerprint(
            incident_id=incident_id, action_type=tool.name, parameters=normalized_parameters,
            environment=environment, risk_level=decision.risk_level,
            policy_id=decision.matched_policy_id, policy_version=decision.policy_version,
        )
        existing = await self.session.scalar(select(RemediationAction).where(
            RemediationAction.idempotency_key == idempotency_key)
            .options(selectinload(RemediationAction.approval))
            .with_for_update())
        if existing is not None:
            if existing.action_fingerprint and existing.action_fingerprint != fingerprint:
                raise AppError("IDEMPOTENCY_KEY_REUSE", "Idempotency key is bound to different action parameters", 409)
            return existing, False
        status = RemediationStatus.PENDING
        if decision.decision is PolicyDecision.REQUIRE_APPROVAL:
            status = RemediationStatus.APPROVAL_REQUIRED
        elif decision.decision is PolicyDecision.DENY:
            status = RemediationStatus.REJECTED
        action = RemediationAction(
            incident_id=incident_id, action_type=tool.name, parameters=normalized_parameters,
            risk_level=decision.risk_level, status=status, requested_by=actor.id, idempotency_key=idempotency_key,
            requested_at=datetime.now(timezone.utc), environment=environment,
            policy_id=decision.matched_policy_id, policy_decision=decision.decision.value,
            policy_version=decision.policy_version, action_fingerprint=fingerprint,
            error=decision.reason if decision.decision is PolicyDecision.DENY else None,
        )
        self.session.add(action)
        await self.session.flush()
        if decision.decision is PolicyDecision.REQUIRE_APPROVAL:
            approval = Approval(
                remediation_action_id=action.id, requested_by=actor.id, status=ApprovalStatus.PENDING,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=self.settings.approval_expiration_minutes),
            )
            action.approval = approval
            self.session.add(approval)
        else:
            action.approval = None
        event = "POLICY_ALLOWED" if decision.decision is PolicyDecision.ALLOW else (
            "APPROVAL_REQUESTED" if decision.decision is PolicyDecision.REQUIRE_APPROVAL else "POLICY_DENIED")
        metadata = {"incident_id": str(incident_id), "tool": tool.name, "environment": environment.value,
                    "risk_level": decision.risk_level.value, "policy_id": str(decision.matched_policy_id) if decision.matched_policy_id else None,
                    "decision": decision.decision.value, "reason": decision.reason}
        self.session.add(AuditLog(actor_id=actor.id, action="POLICY_EVALUATED", resource_type="RemediationAction",
                                  resource_id=str(action.id), result=decision.decision.value, metadata_json=metadata))
        self.session.add(AuditLog(actor_id=actor.id, action=event, resource_type="RemediationAction",
                                  resource_id=str(action.id), result="SUCCESS" if decision.decision is not PolicyDecision.DENY else "DENIED",
                                  metadata_json={"policy_id": str(decision.matched_policy_id) if decision.matched_policy_id else None}))
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            existing = await self.session.scalar(select(RemediationAction).where(RemediationAction.idempotency_key == idempotency_key).options(selectinload(RemediationAction.approval)))
            if existing is not None:
                return existing, False
            raise AppError("REMEDIATION_REQUEST_FAILED", "Remediation request could not be recorded", 503) from exc
        return action, True

    async def execute_action(self, action_id: uuid.UUID) -> RemediationAction:
        action = await self.session.scalar(
            select(RemediationAction).where(RemediationAction.id == action_id)
            .options(selectinload(RemediationAction.approval), selectinload(RemediationAction.requester),
                     selectinload(RemediationAction.incident).selectinload(Incident.service))
            .with_for_update()
        )
        if action is None:
            raise AppError("REMEDIATION_NOT_FOUND", "Remediation action does not exist", 404)
        if action.status is RemediationStatus.COMPLETED:
            return action
        if action.status in {RemediationStatus.REJECTED, RemediationStatus.FAILED, RemediationStatus.CANCELLED}:
            return action
        requester = action.requester
        if requester is None:
            return await self._blocked(action, "EXECUTION_BLOCKED_UNAUTHORIZED", "Requester is no longer available")
        environment = action.incident.service.environment
        if action.incident.status in {IncidentStatus.RESOLVED, IncidentStatus.ESCALATED, IncidentStatus.FAILED}:
            return await self._blocked(action, "INCIDENT_NOT_ACTIONABLE", "The incident no longer permits remediation")
        current = await self.policy_engine.evaluate_action(
            self.session, action_type=action.action_type, environment=environment, risk_level=action.risk_level,
            actor=requester, parameters=action.parameters, registry=self.registry,
            incident_id=action.incident_id, lock_policies=True,
        )
        current_fingerprint = action_fingerprint(
            incident_id=action.incident_id, action_type=action.action_type, parameters=action.parameters,
            environment=environment, risk_level=action.risk_level,
            policy_id=current.matched_policy_id, policy_version=current.policy_version,
        )
        if action.action_fingerprint != current_fingerprint:
            return await self._blocked(action, "EXECUTION_BLOCKED_POLICY_CHANGED", "Action or policy changed after request")
        if current.decision is PolicyDecision.DENY:
            return await self._blocked(action, "POLICY_DENIED", "Current policy denies this action")
        if action.status is RemediationStatus.APPROVAL_REQUIRED:
            return await self._blocked(action, "APPROVAL_REQUIRED", "Valid human approval is required")
        if action.status is RemediationStatus.APPROVED:
            approval = action.approval
            now = datetime.now(timezone.utc)
            if approval is None or approval.status is not ApprovalStatus.APPROVED:
                return await self._blocked(action, "INVALID_APPROVAL", "Approval is not valid")
            if approval.expires_at <= now:
                approval.status = ApprovalStatus.EXPIRED
                return await self._blocked(action, "APPROVAL_EXPIRED", "Approval has expired")
            if current.decision is not PolicyDecision.REQUIRE_APPROVAL:
                return await self._blocked(action, "POLICY_CHANGED", "Current policy no longer requires this approved action")
        elif current.decision is PolicyDecision.REQUIRE_APPROVAL:
            return await self._blocked(action, "APPROVAL_REQUIRED", "Current policy requires human approval")
        tool = self.registry.get(action.action_type)
        action.status = RemediationStatus.EXECUTING
        action.executed_at = datetime.now(timezone.utc)
        await self.session.commit()
        try:
            validated = tool.input_model.model_validate(action.parameters)
            raw = await asyncio.wait_for(tool.handler(self.session, **validated.model_dump()), timeout=self.settings.tool_execution_timeout_seconds)
            action.result = ToolExecutionResult(
                success=True, tool=tool.name, service_id=action.parameters.get("service_id"), execution_id=action.id,
                message=f"{tool.name} completed in the simulator", state_before=raw.get("state_before"),
                state_after=raw.get("state_after"), metadata={key: value for key, value in raw.items() if key not in {"state_before", "state_after"}},
            ).model_dump(mode="json")
            action.status = RemediationStatus.COMPLETED
            action.completed_at = datetime.now(timezone.utc)
            self.session.add(AuditLog(actor_id=action.requested_by, action="REMEDIATION_COMPLETED", resource_type="RemediationAction",
                                      resource_id=str(action.id), result="SUCCESS", metadata_json={"tool": tool.name}))
        except asyncio.TimeoutError:
            self._fail(action, "TOOL_TIMEOUT", "Tool execution timed out", True)
        except AppError as exc:
            self._fail(action, exc.code, exc.message, False)
        except Exception:
            logger.exception("tool_execution_failed", extra={"action_id": str(action.id), "tool": action.action_type})
            self._fail(action, "TOOL_EXECUTION_FAILED", "Simulator tool execution failed", False)
        await self.session.commit()
        return action

    async def _blocked(self, action: RemediationAction, code: str, message: str) -> RemediationAction:
        action.status = RemediationStatus.APPROVAL_REQUIRED if code in {"APPROVAL_REQUIRED", "INVALID_APPROVAL"} else RemediationStatus.REJECTED
        action.error = message
        self.session.add(AuditLog(actor_id=action.requested_by, action="EXECUTION_BLOCKED", resource_type="RemediationAction",
                                  resource_id=str(action.id), result="BLOCKED", metadata_json={"error_code": code}))
        await self.session.commit()
        return action

    def _fail(self, action: RemediationAction, code: str, message: str, retryable: bool) -> None:
        action.status = RemediationStatus.FAILED
        action.error = message
        action.result = ToolFailureResult(tool=action.action_type, execution_id=action.id, error_code=code,
                                          message=message, retryable=retryable).model_dump(mode="json")
        action.completed_at = datetime.now(timezone.utc)
        self.session.add(AuditLog(actor_id=action.requested_by, action="REMEDIATION_FAILED", resource_type="RemediationAction",
                                  resource_id=str(action.id), result="FAILURE", metadata_json={"tool": action.action_type, "error_code": code}))

    async def get_action(self, action_id: uuid.UUID) -> RemediationAction:
        action = await self.session.scalar(
            select(RemediationAction).where(RemediationAction.id == action_id)
            .options(selectinload(RemediationAction.approval))
        )
        if action is None:
            raise AppError("REMEDIATION_NOT_FOUND", "Remediation action does not exist", 404)
        return action
