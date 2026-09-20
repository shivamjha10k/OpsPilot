from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime


class SimulatedServiceState(str, enum.Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"


@dataclass(frozen=True)
class ServiceBaseline:
    cpu_usage: float
    memory_usage: float
    latency_ms: float
    error_rate: float
    request_rate: float
    active_requests: int
    db_connection_utilization: float | None = None
    queue_depth: float | None = None
    worker_utilization: float | None = None


@dataclass
class ServiceState:
    service_id: uuid.UUID
    service_name: str
    environment: str
    version: str
    lifecycle: SimulatedServiceState
    baseline: ServiceBaseline
    metrics: dict[str, float] = field(default_factory=dict)
    dependencies: dict[str, str] = field(default_factory=dict)
    last_updated: datetime | None = None
    tick_count: int = 0
    replicas: int = 1
    workers: int = 1
    cache_generation: int = 0

    def reset(self, now: datetime) -> None:
        self.lifecycle = SimulatedServiceState.NORMAL
        self.metrics = baseline_metrics(self.baseline)
        self.last_updated = now
        self.tick_count = 0
        self.version = "v1.0.0"
        self.replicas = 1
        self.workers = 1
        self.cache_generation = 0

    def snapshot(self) -> dict:
        return {
            "service_id": str(self.service_id),
            "service_name": self.service_name,
            "environment": self.environment,
            "version": self.version,
            "state": self.lifecycle.value,
            "health": "HEALTHY" if self.lifecycle is SimulatedServiceState.NORMAL else self.lifecycle.value,
            "metrics": dict(self.metrics),
            "dependencies": dict(self.dependencies),
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "tick_count": self.tick_count,
            "replicas": self.replicas,
            "workers": self.workers,
            "cache_generation": self.cache_generation,
        }


def baseline_metrics(baseline: ServiceBaseline) -> dict[str, float]:
    values = {
        "cpu_usage": baseline.cpu_usage,
        "memory_usage": baseline.memory_usage,
        "latency_ms": baseline.latency_ms,
        "error_rate": baseline.error_rate,
        "request_rate": baseline.request_rate,
        "active_requests": float(baseline.active_requests),
    }
    if baseline.db_connection_utilization is not None:
        values["db_connection_utilization"] = baseline.db_connection_utilization
    if baseline.queue_depth is not None:
        values["queue_depth"] = baseline.queue_depth
    if baseline.worker_utilization is not None:
        values["worker_utilization"] = baseline.worker_utilization
    return values
