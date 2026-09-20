from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.domain import Alert, AuditLog, Event, EventProcessingStatus, Incident, IncidentStatus, Severity, Service
from app.models.user import Role, User
from app.repositories.alert_repository import AlertRepository
from app.repositories.event_repository import EventRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.service_repository import ServiceRepository
from app.repositories.user_repository import UserRepository


ACTIVE_INCIDENT_STATUSES = frozenset(
    {
        IncidentStatus.DETECTED,
        IncidentStatus.ACKNOWLEDGED,
        IncidentStatus.INVESTIGATING,
        IncidentStatus.DIAGNOSED,
        IncidentStatus.REMEDIATION_PENDING,
        IncidentStatus.APPROVAL_PENDING,
        IncidentStatus.EXECUTING,
        IncidentStatus.VERIFYING,
    }
)

ALLOWED_TRANSITIONS: dict[IncidentStatus, frozenset[IncidentStatus]] = {
    IncidentStatus.DETECTED: frozenset({IncidentStatus.ACKNOWLEDGED, IncidentStatus.ESCALATED}),
    IncidentStatus.ACKNOWLEDGED: frozenset({IncidentStatus.INVESTIGATING, IncidentStatus.ESCALATED}),
    IncidentStatus.INVESTIGATING: frozenset({IncidentStatus.DIAGNOSED, IncidentStatus.ESCALATED}),
    IncidentStatus.DIAGNOSED: frozenset({IncidentStatus.REMEDIATION_PENDING, IncidentStatus.ESCALATED}),
    IncidentStatus.REMEDIATION_PENDING: frozenset({IncidentStatus.APPROVAL_PENDING, IncidentStatus.ESCALATED}),
    IncidentStatus.APPROVAL_PENDING: frozenset({IncidentStatus.EXECUTING, IncidentStatus.ESCALATED}),
    IncidentStatus.EXECUTING: frozenset({IncidentStatus.VERIFYING, IncidentStatus.ESCALATED}),
    IncidentStatus.VERIFYING: frozenset({IncidentStatus.RESOLVED, IncidentStatus.FAILED, IncidentStatus.ESCALATED}),
    IncidentStatus.FAILED: frozenset({IncidentStatus.ESCALATED}),
    IncidentStatus.ESCALATED: frozenset(),
    IncidentStatus.RESOLVED: frozenset(),
}


class IncidentStateMachine:
    """Single source of truth for incident lifecycle transitions."""

    @staticmethod
    def transition(incident: Incident, target: IncidentStatus) -> bool:
        if incident.status == target:
            return False
        if target not in ALLOWED_TRANSITIONS.get(incident.status, frozenset()):
            raise AppError(
                "INVALID_STATE_TRANSITION",
                f"Cannot transition incident from {incident.status.value} to {target.value}",
                409,
            )
        incident.status = target
        if target is IncidentStatus.RESOLVED:
            incident.resolved_at = datetime.now(timezone.utc)
        return True


@dataclass(frozen=True)
class NormalizedAlert:
    alert_type: str
    severity: Severity
    message: str
    payload: dict


class AlertNormalizer:
    """Maps generic operational events into explainable alert records."""

    _severity_by_token = (
        (("health", "unhealthy", "failure", "failed"), Severity.CRITICAL),
        (("db_connection", "connection_exhaustion", "database_connection"), Severity.CRITICAL),
        (("cpu", "latency", "error_rate", "metric.alert", "threshold", "spike"), Severity.HIGH),
    )

    @classmethod
    def normalize(cls, event: Event) -> NormalizedAlert | None:
        payload = dict(event.payload or {})
        event_type = event.event_type.strip().lower()
        raw_severity = payload.get("severity")
        if raw_severity is not None:
            try:
                severity = Severity(str(raw_severity).strip().upper())
            except ValueError as exc:
                raise AppError("INVALID_ALERT", "severity must be LOW, MEDIUM, HIGH, or CRITICAL", 422) from exc
        else:
            if payload.get("alert") is False or event_type.startswith(("deployment", "info", "audit")):
                return None
            severity = next(
                (level for tokens, level in cls._severity_by_token if any(token in event_type for token in tokens)),
                None,
            )
            if severity is None:
                return None

        alert_type = str(payload.get("alert_type") or event.event_type).strip().upper()
        if not alert_type:
            raise AppError("INVALID_ALERT", "alert_type must not be blank", 422)
        message = str(payload.get("message") or cls._fact_message(event, payload)).strip()
        if not message:
            raise AppError("INVALID_ALERT", "alert message must not be blank", 422)
        normalized_payload = {"event_id": event.event_id, "event_type": event.event_type, "event": payload}
        return NormalizedAlert(alert_type, severity, message, normalized_payload)

    @staticmethod
    def _fact_message(event: Event, payload: dict) -> str:
        facts = [f"{event.event_type} reported by {event.source}"]
        for key in ("metric", "value", "threshold", "status"):
            if key in payload:
                facts.append(f"{key}={payload[key]}")
        return "; ".join(facts)


def _severity_compatible(left: Severity, right: Severity) -> bool:
    rank = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3, Severity.CRITICAL: 4}
    return abs(rank[left] - rank[right]) <= 1 or min(rank[left], rank[right]) >= 3


def _alert_type_group(alert_type: str) -> str:
    value = alert_type.lower()
    groups = {
        "database": ("db", "database", "connection"),
        "latency": ("latency", "timeout"),
        "error": ("error", "failure", "failed"),
        "health": ("health", "availability", "down"),
        "capacity": ("cpu", "memory", "disk", "capacity"),
    }
    for group, tokens in groups.items():
        if any(token in value for token in tokens):
            return group
    return value


def _alerts_compatible(left: Alert, right: Alert) -> bool:
    return (
        left.alert_type == right.alert_type
        or _alert_type_group(left.alert_type) == _alert_type_group(right.alert_type)
        or (left.severity in {Severity.HIGH, Severity.CRITICAL} and right.severity in {Severity.HIGH, Severity.CRITICAL})
    ) and _severity_compatible(left.severity, right.severity)


@dataclass(frozen=True)
class IngestionResult:
    event: Event
    alert: Alert | None
    incident: Incident | None
    duplicate: bool


class IncidentEngine:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventRepository(session)
        self.alerts = AlertRepository(session)
        self.incidents = IncidentRepository(session)
        self.services = ServiceRepository(session)
        self.users = UserRepository(session)

    async def persist_event(self, event: Event, *, request_id: str | None = None) -> tuple[Event, bool]:
        existing = await self.events.get_by_event_id(event.event_id)
        if existing is not None:
            return existing, True
        service = await self.services.get_by_id(event.service_id)
        if service is None:
            raise AppError("SERVICE_NOT_FOUND", "Service does not exist", 404)
        event.request_id = request_id
        event.processing_status = EventProcessingStatus.PERSISTED
        try:
            await self.events.create(event)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.events.get_by_event_id(event.event_id)
            if existing is None:
                raise AppError("DUPLICATE_EVENT", "Event could not be persisted", 409)
            return existing, True
        return event, False

    async def mark_queued(self, event_id: str, task_id: str | None = None) -> Event:
        event = await self.events.get_by_event_id(event_id)
        if event is None:
            raise AppError("EVENT_NOT_FOUND", "Event does not exist", 404)
        if event.processing_status is not EventProcessingStatus.PROCESSED:
            event.processing_status = EventProcessingStatus.QUEUED
            event.task_id = task_id
            await self.session.commit()
        return event

    async def set_task_id(self, event_id: str, task_id: str) -> Event:
        event = await self.events.get_by_event_id(event_id)
        if event is None:
            raise AppError("EVENT_NOT_FOUND", "Event does not exist", 404)
        if event.processing_status is not EventProcessingStatus.PROCESSED:
            event.task_id = task_id
            await self.session.commit()
        return event

    async def mark_queue_failed(self, event_id: str, error: str) -> Event:
        event = await self.events.get_by_event_id(event_id)
        if event is None:
            raise AppError("EVENT_NOT_FOUND", "Event does not exist", 404)
        event.processing_status = EventProcessingStatus.FAILED
        event.last_processing_error = error[:2000]
        await self.session.commit()
        return event

    async def process_event(self, event_id: str, *, actor_id: uuid.UUID | None = None,
                            request_id: str | None = None) -> IngestionResult:
        event = await self.session.scalar(
            select(Event).options(selectinload(Event.service)).where(Event.event_id == event_id).with_for_update()
        )
        if event is None:
            raise AppError("EVENT_NOT_FOUND", "Event does not exist", 404)
        if event.processed or event.processing_status is EventProcessingStatus.PROCESSED:
            alert = await self.alerts.get_by_event_id(event.event_id)
            incident = None
            if alert:
                from app.models.domain import incident_alerts
                incident_id = await self.session.scalar(
                    select(incident_alerts.c.incident_id).where(incident_alerts.c.alert_id == alert.id)
                )
                if incident_id:
                    incident = await self.incidents.get_by_id(incident_id)
            return IngestionResult(event, alert, incident, True)

        event.processing_status = EventProcessingStatus.PROCESSING
        event.processing_attempts += 1
        event.last_processing_error = None
        event.request_id = request_id or event.request_id
        await self.session.flush()
        try:
            service = event.service
            if service is None:
                raise AppError("SERVICE_NOT_FOUND", "Service does not exist", 404)
            normalized = AlertNormalizer.normalize(event)
            alert = None
            incident = None
            if normalized is not None:
                alert = await self.alerts.get_by_event_id(event.event_id)
                if alert is None:
                    alert = Alert(
                        service_id=event.service_id, source=event.source, alert_type=normalized.alert_type,
                        severity=normalized.severity, message=normalized.message, payload=normalized.payload,
                        occurred_at=event.occurred_at,
                    )
                    await self.alerts.create(alert)
                incident = await self._correlate_or_create(alert, service, actor_id)
            event.processed = True
            event.processing_status = EventProcessingStatus.PROCESSED
            event.processed_at = datetime.now(timezone.utc)
            await self.session.flush()
            await self.session.commit()
            return IngestionResult(event, alert, incident, False)
        except AppError as exc:
            await self.session.rollback()
            await self._record_failure(event_id, str(exc))
            raise
        except Exception as exc:
            await self.session.rollback()
            await self._record_retryable_failure(event_id, str(exc))
            raise

    async def ingest(self, event: Event, actor: User | None = None) -> IngestionResult:
        persisted, duplicate = await self.persist_event(event)
        if duplicate:
            return IngestionResult(persisted, await self.alerts.get_by_event_id(persisted.event_id), None, True)
        result = await self.process_event(persisted.event_id, actor_id=actor.id if actor else None)
        if result.incident and not result.duplicate:
            await self.dispatch_pending_investigations(result.incident.id)
        return result

    async def reprocess_event(self, event_id: str, *, request_id: str | None = None) -> IngestionResult:
        """Retry a persisted or failed event without creating a second event."""
        return await self.process_event(event_id, request_id=request_id)

    async def _record_failure(self, event_id: str, error: str) -> None:
        event = await self.events.get_by_event_id(event_id)
        if event is not None:
            event.processing_status = EventProcessingStatus.FAILED
            event.last_processing_error = error[:2000]
            await self.session.commit()

    async def _record_retryable_failure(self, event_id: str, error: str) -> None:
        event = await self.events.get_by_event_id(event_id)
        if event is not None:
            event.processing_status = EventProcessingStatus.QUEUED
            event.last_processing_error = error[:2000]
            await self.session.commit()

    async def _correlate_or_create(self, alert: Alert, service: Service, actor: User | uuid.UUID | None) -> Incident:
        settings = get_settings()
        candidates = await self.incidents.get_active_for_service(service.id, ACTIVE_INCIDENT_STATUSES)
        window = timedelta(minutes=settings.incident_correlation_window_minutes)
        for incident in candidates:
            if abs(incident.detected_at - alert.occurred_at) <= window and incident.alerts:
                if any(_alerts_compatible(existing, alert) for existing in incident.alerts):
                    incident.alerts.append(alert)
                    await self._audit(
                        actor, "ALERT_ASSOCIATED", "Incident", str(incident.id),
                        {"alert_id": str(alert.id), "alert_type": alert.alert_type},
                    )
                    await self.session.flush()
                    return incident

        incident = Incident(
            incident_number=self._incident_number(),
            title=self._title(service.name, alert),
            description=alert.message,
            service_id=service.id,
            severity=alert.severity,
            status=IncidentStatus.DETECTED,
            detected_at=alert.occurred_at,
        )
        incident.alerts.append(alert)
        self.session.add(incident)
        await self.session.flush()

        from app.models.domain import AIInvestigation, InvestigationStatus, RiskLevel
        investigation = AIInvestigation(
            incident_id=incident.id,
            model=get_settings().ai_model,
            summary="Investigation queued.",
            root_cause="Not yet determined.",
            confidence=0,
            evidence={},
            recommendation="No action has been executed.",
            risk_level=RiskLevel.LOW,
            status=InvestigationStatus.PENDING,
            prompt_version=get_settings().ai_prompt_version,
            requested_by=actor.id if isinstance(actor, User) else actor
        )
        self.session.add(investigation)
        await self.session.flush()

        await self._audit(actor, "INCIDENT_CREATED", "Incident", str(incident.id), {"alert_id": str(alert.id)})
        await self._audit(actor, "ALERT_ASSOCIATED", "Incident", str(incident.id), {"alert_id": str(alert.id)})
        return incident

    @staticmethod
    def _incident_number() -> str:
        return f"INC-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:10].upper()}"

    @staticmethod
    def _title(service_name: str, alert: Alert) -> str:
        label = alert.alert_type.replace("_", " ").replace(".", " ").title()
        return f"{label} on {service_name}"

    async def create_manual(self, *, title: str, description: str, service_id: uuid.UUID,
                            severity: Severity, detected_at: datetime | None, actor: User) -> Incident:
        if await self.services.get_by_id(service_id) is None:
            raise AppError("SERVICE_NOT_FOUND", "Service does not exist", 404)
        detection_time = detected_at or datetime.now(timezone.utc)
        if detection_time > datetime.now(timezone.utc):
            raise AppError("INVALID_INCIDENT", "detected_at cannot be in the future", 422)
        incident = Incident(
            incident_number=self._incident_number(), title=title, description=description,
            service_id=service_id, severity=severity, status=IncidentStatus.DETECTED,
            detected_at=detection_time,
        )
        self.session.add(incident)
        await self.session.flush()
        await self._audit(actor, "INCIDENT_CREATED", "Incident", str(incident.id), {"manual": True})
        await self.session.commit()
        return incident

    async def acknowledge(self, incident_id: uuid.UUID, actor: User) -> Incident:
        incident = await self._locked_incident(incident_id)
        if incident.status is IncidentStatus.ACKNOWLEDGED:
            return incident
        changed = IncidentStateMachine.transition(incident, IncidentStatus.ACKNOWLEDGED)
        if changed:
            incident.acknowledged_at = datetime.now(timezone.utc)
            await self._audit(actor, "INCIDENT_ACKNOWLEDGED", "Incident", str(incident.id), {})
        await self.session.commit()
        return incident

    async def assign(self, incident_id: uuid.UUID, target_user_id: uuid.UUID, actor: User) -> Incident:
        incident = await self._locked_incident(incident_id)
        target = await self.users.get_by_id(target_user_id)
        if target is None or not target.is_active or target.role not in {Role.ENGINEER, Role.ADMIN}:
            raise AppError("INVALID_ASSIGNMENT_TARGET", "Assignment target must be an active engineer or admin", 422)
        if incident.status in {IncidentStatus.RESOLVED, IncidentStatus.ESCALATED}:
            raise AppError("INVALID_INCIDENT_OPERATION", "This incident cannot be assigned", 409)
        if incident.assigned_to != target.id:
            old = str(incident.assigned_to) if incident.assigned_to else None
            incident.assigned_to = target.id
            await self._audit(actor, "INCIDENT_ASSIGNED", "Incident", str(incident.id), {"old_user_id": old, "user_id": str(target.id)})
        await self.session.commit()
        return incident

    async def escalate(self, incident_id: uuid.UUID, actor: User) -> Incident:
        incident = await self._locked_incident(incident_id)
        if incident.status is IncidentStatus.ESCALATED:
            return incident
        if incident.status is IncidentStatus.RESOLVED:
            raise AppError("INVALID_INCIDENT_OPERATION", "A resolved incident cannot be escalated", 409)
        IncidentStateMachine.transition(incident, IncidentStatus.ESCALATED)
        await self._audit(actor, "INCIDENT_ESCALATED", "Incident", str(incident.id), {})
        await self.session.commit()
        return incident

    async def transition(self, incident_id: uuid.UUID, target: IncidentStatus, actor: User) -> Incident:
        incident = await self._locked_incident(incident_id)
        changed = IncidentStateMachine.transition(incident, target)
        if changed:
            await self._audit(actor, "INCIDENT_STATUS_CHANGED", "Incident", str(incident.id), {"status": target.value})
        await self.session.commit()
        return incident

    async def _locked_incident(self, incident_id: uuid.UUID) -> Incident:
        incident = await self.session.scalar(
            select(Incident).where(Incident.id == incident_id).with_for_update().options(selectinload(Incident.alerts))
        )
        if incident is None:
            raise AppError("INCIDENT_NOT_FOUND", "Incident does not exist", 404)
        return incident

    async def _audit(self, actor: User | uuid.UUID | None, action: str, resource_type: str, resource_id: str, metadata: dict) -> None:
        self.session.add(AuditLog(
            actor_id=actor.id if isinstance(actor, User) else actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result="SUCCESS",
            metadata_json=metadata,
        ))

    async def dispatch_pending_investigations(self, incident_id: uuid.UUID) -> None:
        from app.models.domain import AIInvestigation, InvestigationStatus
        from app.workers.tasks.investigation_tasks import investigate_incident_task
        investigations = await self.session.scalars(
            select(AIInvestigation)
            .where(AIInvestigation.incident_id == incident_id)
            .where(AIInvestigation.status == InvestigationStatus.PENDING)
            .where(AIInvestigation.task_id.is_(None))
            .with_for_update(skip_locked=True)
        )
        for inv in investigations:
            try:
                task = investigate_incident_task.apply_async(args=[str(incident_id), str(inv.id)])
                inv.task_id = task.id
                self.session.add(inv)
            except Exception as exc:
                raise AppError("DISPATCH_FAILED", f"Failed to dispatch investigation: {exc}", 503) from exc
        await self.session.commit()

