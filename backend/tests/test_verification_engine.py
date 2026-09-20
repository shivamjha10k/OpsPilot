from app.verification.engine import VerificationEngine
from app.verification.schemas import VerificationCriteria


def test_combined_recovery_criteria_uses_actual_state() -> None:
    criteria = VerificationCriteria(max_cpu_usage=70, max_error_rate=0.02, max_latency_ms=250)
    checks = VerificationEngine._checks(
        {"health": "HEALTHY"},
        {"cpu_usage": 65, "error_rate": 0.01, "latency_ms": 120},
        criteria,
    )

    assert all(check.passed for check in checks)


def test_unhealthy_state_cannot_pass_verification() -> None:
    criteria = VerificationCriteria(max_memory_usage=70)
    checks = VerificationEngine._checks(
        {"health": "FAILED"},
        {"memory_usage": 60},
        criteria,
    )

    assert any(check.name == "service_health" and not check.passed for check in checks)


def test_scenario_criteria_are_specific() -> None:
    incident = type("IncidentLike", (), {"alerts": [type("AlertLike", (), {
        "payload": {"event": {"scenario": "db_connection_exhaustion"}},
    })()]})()

    criteria = VerificationEngine.criteria_for(incident)

    assert criteria.max_db_connection_utilization == 80
    assert criteria.max_error_rate == 0.02
    assert criteria.max_latency_ms == 250