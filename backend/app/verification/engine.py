from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.models.domain import AuditLog, Incident, IncidentStatus, RemediationAction
from app.services.incident_engine import IncidentStateMachine

from .schemas import VerificationCheck, VerificationCriteria, VerificationResult, VerificationStatus


class VerificationEngine:
    """Evaluates fresh persisted simulator state; it never infers recovery from execution success."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def verify_remediation(self, action_id: uuid.UUID, criteria: VerificationCriteria | None = None) -> VerificationResult:
        action = await self.session.scalar(
            select(RemediationAction)
            .where(RemediationAction.id == action_id)
            .options(selectinload(RemediationAction.incident).selectinload(Incident.service),
                     selectinload(RemediationAction.incident).selectinload(Incident.alerts))
            .with_for_update()
        )
        if action is None:
            raise AppError("REMEDIATION_NOT_FOUND", "Remediation action does not exist", 404)
        incident = action.incident
        if incident is None or incident.service is None:
            raise AppError("INCIDENT_NOT_FOUND", "Incident does not exist", 404)
        criteria = criteria or self.criteria_for(incident)
        result_data = dict(action.result or {})
        history = list(result_data.get("verification", []))
        attempt = len(history) + 1
        previous_successes = int(result_data.get("consecutive_verification_successes", 0))
        state = dict(incident.service.simulation_state or {})
        metrics = dict(state.get("metrics") or {})
        checks = self._checks(state, metrics, criteria)
        passed = all(item.passed for item in checks)
        successes = previous_successes + 1 if passed else 0
        status = VerificationStatus.RECOVERED if successes >= criteria.consecutive_successes else VerificationStatus.NOT_RECOVERED
        result = VerificationResult(
            status=status, attempt=attempt, consecutive_successes=successes,
            checks=checks, observed={"state": state.get("state"), "health": state.get("health"), **metrics},
            criteria=criteria,
            reason="Recovery criteria satisfied" if status is VerificationStatus.RECOVERED else "Recovery criteria not satisfied",
        )
        history.append(result.model_dump(mode="json"))
        action.result = {
            **result_data,
            "verification": history[-10:],
            "verification_status": status.value,
            "consecutive_verification_successes": successes,
        }
        event = "VERIFICATION_PASSED" if status is VerificationStatus.RECOVERED else "VERIFICATION_FAILED"
        self.session.add(AuditLog(
            actor_id=None, action="VERIFICATION_ATTEMPT", resource_type="RemediationAction",
            resource_id=str(action.id), result=status.value,
            metadata_json={"incident_id": str(incident.id), "attempt": attempt, "checks": [check.model_dump() for check in checks]},
        ))
        self.session.add(AuditLog(
            actor_id=None, action=event, resource_type="Incident", resource_id=str(incident.id),
            result="SUCCESS" if status is VerificationStatus.RECOVERED else "FAILURE",
            metadata_json={"remediation_action_id": str(action.id), "attempt": attempt},
        ))
        if status is VerificationStatus.RECOVERED:
            if incident.status is IncidentStatus.VERIFYING:
                IncidentStateMachine.transition(incident, IncidentStatus.RESOLVED)
                self.session.add(AuditLog(
                    actor_id=None, action="INCIDENT_RESOLVED", resource_type="Incident", resource_id=str(incident.id),
                    result="SUCCESS", metadata_json={"remediation_action_id": str(action.id), "verification_attempt": attempt},
                ))
        await self.session.commit()
        return result

    @staticmethod
    def criteria_for(incident: Incident) -> VerificationCriteria:
        scenario = None
        for alert in incident.alerts or []:
            scenario = (alert.payload or {}).get("event", {}).get("scenario") or (alert.payload or {}).get("scenario")
            if scenario:
                break
        criteria = {
            "high_cpu": {"max_cpu_usage": 70, "max_error_rate": 0.02, "max_latency_ms": 250},
            "error_spike": {"max_error_rate": 0.02, "max_latency_ms": 250},
            "db_connection_exhaustion": {"max_db_connection_utilization": 80, "max_error_rate": 0.02, "max_latency_ms": 250},
            "queue_backlog": {"max_queue_depth": 100, "max_worker_utilization": 80, "max_latency_ms": 250},
            "memory_leak": {"max_memory_usage": 70, "max_error_rate": 0.02, "max_latency_ms": 250},
            "failed_deployment": {"max_error_rate": 0.02, "max_latency_ms": 250, "required_deployment_state": "v1.0.0"},
        }.get(scenario, {})
        return VerificationCriteria(**criteria)

    @staticmethod
    def _checks(state: dict, metrics: dict, criteria: VerificationCriteria) -> list[VerificationCheck]:
        checks: list[VerificationCheck] = []
        if criteria.health_required:
            health = state.get("health")
            checks.append(VerificationCheck(name="service_health", passed=health == "HEALTHY", observed=health, expected="HEALTHY"))
        fields = (
            ("error_rate", criteria.max_error_rate), ("latency_ms", criteria.max_latency_ms),
            ("cpu_usage", criteria.max_cpu_usage), ("memory_usage", criteria.max_memory_usage),
            ("db_connection_utilization", criteria.max_db_connection_utilization),
            ("queue_depth", criteria.max_queue_depth), ("worker_utilization", criteria.max_worker_utilization),
        )
        for name, maximum in fields:
            if maximum is not None:
                value = metrics.get(name)
                checks.append(VerificationCheck(name=name, passed=value is not None and value <= maximum, observed=value, expected=maximum))
        if criteria.required_deployment_state is not None:
            checks.append(VerificationCheck(name="deployment_state", passed=state.get("version") == criteria.required_deployment_state,
                                            observed=state.get("version"), expected=criteria.required_deployment_state))
        return checks