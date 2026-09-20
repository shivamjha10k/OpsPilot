from datetime import datetime, timezone

import pytest

from app.core.errors import AppError
from app.models.domain import Event, Incident, IncidentStatus, Severity
from app.services.incident_engine import ALLOWED_TRANSITIONS, AlertNormalizer, IncidentStateMachine


def make_incident(status: IncidentStatus) -> Incident:
    return Incident(
        incident_number="INC-TEST-1",
        title="Test incident",
        description="Observed test condition",
        service_id=__import__("uuid").uuid4(),
        severity=Severity.HIGH,
        status=status,
        detected_at=datetime.now(timezone.utc),
    )


def test_every_declared_state_transition_is_allowed() -> None:
    for source, targets in ALLOWED_TRANSITIONS.items():
        for target in targets:
            incident = make_incident(source)
            assert IncidentStateMachine.transition(incident, target) is True
            assert incident.status is target


def test_invalid_state_transition_is_rejected() -> None:
    with pytest.raises(AppError, match="Cannot transition"):
        IncidentStateMachine.transition(make_incident(IncidentStatus.DETECTED), IncidentStatus.RESOLVED)


def test_normalizer_creates_high_alert_from_cpu_event() -> None:
    event = Event(
        event_id="evt-1", event_type="metric.alert", source="monitor",
        service_id=__import__("uuid").uuid4(), payload={"metric": "cpu_usage", "value": 95.2},
        occurred_at=datetime.now(timezone.utc),
    )
    alert = AlertNormalizer.normalize(event)
    assert alert is not None
    assert alert.severity is Severity.HIGH
    assert alert.alert_type == "METRIC.ALERT"


def test_normalizer_rejects_unknown_explicit_severity() -> None:
    event = Event(
        event_id="evt-2", event_type="health.alert", source="monitor",
        service_id=__import__("uuid").uuid4(), payload={"severity": "urgent"},
        occurred_at=datetime.now(timezone.utc),
    )
    with pytest.raises(AppError) as error:
        AlertNormalizer.normalize(event)
    assert error.value.code == "INVALID_ALERT"


def test_informational_event_is_stored_without_alert() -> None:
    event = Event(
        event_id="evt-3", event_type="deployment.completed", source="deployments",
        service_id=__import__("uuid").uuid4(), payload={}, occurred_at=datetime.now(timezone.utc),
    )
    assert AlertNormalizer.normalize(event) is None
