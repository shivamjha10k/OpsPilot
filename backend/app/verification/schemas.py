from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VerificationStatus(str, enum.Enum):
    RECOVERED = "RECOVERED"
    NOT_RECOVERED = "NOT_RECOVERED"
    ESCALATED = "ESCALATED"


class VerificationCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    health_required: bool = True
    max_error_rate: float | None = Field(default=None, ge=0)
    max_latency_ms: float | None = Field(default=None, ge=0)
    max_cpu_usage: float | None = Field(default=None, ge=0, le=100)
    max_memory_usage: float | None = Field(default=None, ge=0, le=100)
    max_db_connection_utilization: float | None = Field(default=None, ge=0, le=100)
    max_queue_depth: float | None = Field(default=None, ge=0)
    max_worker_utilization: float | None = Field(default=None, ge=0, le=100)
    required_deployment_state: str | None = None
    consecutive_successes: int = Field(default=1, ge=1, le=10)


class VerificationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    observed: Any = None
    expected: Any = None


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus
    attempt: int = Field(ge=1)
    consecutive_successes: int = Field(ge=0)
    checks: list[VerificationCheck]
    observed: dict[str, Any]
    criteria: VerificationCriteria
    reason: str