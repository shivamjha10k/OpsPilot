from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioDefinition:
    name: str
    description: str
    target_services: tuple[str, ...]
    trigger: str
    telemetry_pattern: tuple[str, ...]
    expected_root_cause: str
    expected_evidence: tuple[str, ...]
    recommended_action: str
    risk_level: str
    recovery_conditions: tuple[str, ...]
    duration: str = "until stopped"

    def metadata(self) -> dict:
        return {
            "scenario": self.name,
            "description": self.description,
            "target_services": list(self.target_services),
            "trigger": self.trigger,
            "telemetry_pattern": list(self.telemetry_pattern),
            "expected_root_cause": self.expected_root_cause,
            "expected_evidence": list(self.expected_evidence),
            "recommended_action": self.recommended_action,
            "risk_level": self.risk_level,
            "recovery_conditions": list(self.recovery_conditions),
            "duration": self.duration,
        }


SCENARIOS: dict[str, ScenarioDefinition] = {
    "high_cpu": ScenarioDefinition(
        "high_cpu", "Sustained CPU saturation", ("payment-service",),
        "cpu_usage rises above 90%", ("cpu_usage", "latency_ms", "error_rate"),
        "CPU saturation", ("CPU above threshold", "latency increase", "resource exhaustion log"),
        "restart_service or scale_service", "MEDIUM", ("CPU below 70%", "latency near baseline", "error rate normal"),
    ),
    "error_spike": ScenarioDefinition(
        "error_spike", "Sharp increase in request failures", ("order-service",),
        "5xx/error rate increases sharply", ("error_rate", "latency_ms", "health"),
        "Application error spike", ("error rate above threshold", "error logs", "health degradation"),
        "restart_service or rollback_deployment", "HIGH", ("error rate returns to baseline", "health is healthy"),
    ),
    "db_connection_exhaustion": ScenarioDefinition(
        "db_connection_exhaustion", "Database connection pool exhaustion", ("payment-service",),
        "database connection utilization reaches 98-100%", ("db_connection_utilization", "latency_ms", "error_rate"),
        "Database connection pool exhaustion", ("DB utilization critical", "timeouts", "connection failure logs"),
        "rollback or scale_service", "HIGH", ("DB utilization below safe threshold", "timeouts stop", "latency normalizes"),
    ),
    "queue_backlog": ScenarioDefinition(
        "queue_backlog", "Notification queue continuously grows", ("notification-service",),
        "queue depth rises while workers approach saturation", ("queue_depth", "worker_utilization", "latency_ms"),
        "Insufficient notification worker capacity", ("queue backlog", "worker saturation", "processing delay"),
        "scale_workers", "MEDIUM", ("queue depth trends toward baseline", "worker utilization normal"),
    ),
    "memory_leak": ScenarioDefinition(
        "memory_leak", "User service memory usage increases over time", ("user-service",),
        "memory usage continuously increases", ("memory_usage", "latency_ms", "error_rate"),
        "Memory leak", ("memory pressure", "allocation pressure", "latency increase"),
        "restart_service", "MEDIUM", ("service restart resets memory", "latency normalizes"),
    ),
    "failed_deployment": ScenarioDefinition(
        "failed_deployment", "A bad order-service deployment degrades health", ("order-service",),
        "new deployment changes the service version", ("deployment", "error_rate", "latency_ms", "health"),
        "Failed deployment", ("failed deployment record", "health check failure", "correlated error spike"),
        "rollback_deployment", "HIGH", ("a later rollback restores baseline", "health checks pass"),
    ),
}


def get_scenario(name: str) -> ScenarioDefinition:
    try:
        return SCENARIOS[name]
    except KeyError as exc:
        raise KeyError(name) from exc
