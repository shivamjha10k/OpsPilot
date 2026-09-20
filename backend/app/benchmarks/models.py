from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class TrialStatus(str, enum.Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ScenarioGroundTruth:
    scenario: str
    trigger_condition: str
    expected_root_cause: str
    acceptable_root_causes: frozenset[str]
    expected_evidence: tuple[str, ...]
    expected_action: str
    acceptable_actions: frozenset[str]
    expected_risk_level: str
    recovery_conditions: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkConfig:
    scenarios: tuple[str, ...]
    trials: int = 10
    seed: int = 20260909
    warmup: int = 0
    cooldown_seconds: float = 0.0
    consecutive_successes: int = 1
    benchmark_version: str = "phase15-v1"

    def __post_init__(self) -> None:
        if self.trials < 1:
            raise ValueError("trials must be positive")
        if self.warmup < 0 or self.cooldown_seconds < 0:
            raise ValueError("warmup and cooldown must not be negative")
        if self.consecutive_successes < 1:
            raise ValueError("consecutive_successes must be positive")
        if not self.scenarios:
            raise ValueError("at least one scenario is required")


@dataclass
class TrialResult:
    scenario: str
    seed: int
    trial_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    mode: str = "OPSPILOT"
    status: TrialStatus = TrialStatus.FAILED
    failure_reason: str | None = None
    timestamps: dict[str, datetime | None] = field(default_factory=dict)
    root_cause: str | None = None
    recommendation_action: str | None = None
    risk_level: str | None = None
    rag_relevant_documents: set[str] = field(default_factory=set)
    rag_retrieved_documents: list[str] = field(default_factory=list)
    automation_eligible: bool = False
    approval_outcome: str | None = None
    execution_success: bool | None = None
    verification_success: bool | None = None
    unsafe_action_attempts: int = 0
    unsafe_executions: int = 0
    metrics: dict[str, float] = field(default_factory=dict)

    def validate(self) -> None:
        if self.status is not TrialStatus.VALID:
            return
        for name, value in self.timestamps.items():
            if value is not None and value.tzinfo is None:
                raise ValueError(f"timestamp {name} must be timezone-aware")
        ordered = [value for value in self.timestamps.values() if value is not None]
        if any(left > right for left, right in zip(ordered, ordered[1:])):
            raise ValueError("trial timestamps are not chronological")
        if self.unsafe_action_attempts < 0 or self.unsafe_executions < 0:
            raise ValueError("unsafe action counts must not be negative")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "scenario": self.scenario, "seed": self.seed, "trial_id": self.trial_id, "mode": self.mode,
            "status": self.status.value, "failure_reason": self.failure_reason,
            "timestamps": {key: value.isoformat() if value else None for key, value in self.timestamps.items()},
            "root_cause": self.root_cause, "recommendation_action": self.recommendation_action,
            "risk_level": self.risk_level, "rag_relevant_documents": sorted(self.rag_relevant_documents),
            "rag_retrieved_documents": self.rag_retrieved_documents, "automation_eligible": self.automation_eligible,
            "approval_outcome": self.approval_outcome, "execution_success": self.execution_success,
            "verification_success": self.verification_success, "unsafe_action_attempts": self.unsafe_action_attempts,
            "unsafe_executions": self.unsafe_executions, "metrics": self.metrics,
        }


@dataclass
class BenchmarkRun:
    benchmark_run_id: str
    created_at: datetime
    configuration: BenchmarkConfig
    trials: list[TrialResult]
    environment: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_run_id": self.benchmark_run_id, "created_at": self.created_at.isoformat(),
            "configuration": {**self.configuration.__dict__}, "environment": self.environment,
            "trials": [trial.to_dict() for trial in self.trials],
        }
