from __future__ import annotations

import math
import statistics
from datetime import datetime
from typing import Iterable

from .models import TrialResult, TrialStatus

TIMESTAMP_ORDER = (
    "trigger_at", "detected_at", "acknowledged_at", "investigation_started_at", "diagnosed_at",
    "remediation_requested_at", "approval_requested_at", "approval_completed_at", "execution_started_at",
    "execution_completed_at", "verification_started_at", "verification_completed_at", "resolved_at", "escalated_at",
)


def seconds_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return (end - start).total_seconds()


def timestamp_metrics(trial: TrialResult) -> dict[str, float | None]:
    values = trial.timestamps
    return {
        "mttd_seconds": seconds_between(values.get("trigger_at"), values.get("detected_at")),
        "mtti_seconds": seconds_between(values.get("detected_at"), values.get("diagnosed_at")),
        "mttr_seconds": seconds_between(values.get("trigger_at"), values.get("resolved_at")),
        "investigation_seconds": seconds_between(values.get("investigation_started_at"), values.get("diagnosed_at")),
        "approval_seconds": seconds_between(values.get("approval_requested_at"), values.get("approval_completed_at")),
        "execution_seconds": seconds_between(values.get("execution_started_at"), values.get("execution_completed_at")),
        "verification_seconds": seconds_between(values.get("verification_started_at"), values.get("verification_completed_at")),
    }


def summarize_trials(trials: Iterable[TrialResult], metric: str) -> dict[str, float | int | None]:
    values = []
    for trial in trials:
        if trial.status is not TrialStatus.VALID:
            continue
        value = timestamp_metrics(trial).get(metric, trial.metrics.get(metric))
        if value is not None and math.isfinite(value):
            values.append(float(value))
    if not values:
        return {"count": 0, "mean": None, "median": None, "minimum": None, "maximum": None, "stdev": None, "p95": None}
    ordered = sorted(values)
    return {
        "count": len(values), "mean": statistics.fmean(values), "median": statistics.median(values),
        "minimum": min(values), "maximum": max(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "p95": ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)],
    }


def rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def outcome_summary(trials: Iterable[TrialResult]) -> dict[str, float | int | None]:
    values = list(trials)
    valid = [trial for trial in values if trial.status is TrialStatus.VALID]
    executed = [trial for trial in valid if trial.execution_success is not None]
    verified = [trial for trial in valid if trial.verification_success is not None]
    approvals = [trial for trial in valid if trial.approval_outcome in {"APPROVED", "REJECTED", "EXPIRED"}]
    eligible = [trial for trial in valid if trial.automation_eligible]
    return {
        "total_trials": len(values), "valid_trials": len(valid),
        "invalid_trials": sum(trial.status is TrialStatus.INVALID for trial in values),
        "failed_trials": sum(trial.status is TrialStatus.FAILED for trial in values),
        "execution_success_rate": rate(sum(trial.execution_success is True for trial in executed), len(executed)),
        "verification_success_rate": rate(sum(trial.verification_success is True for trial in verified), len(verified)),
        "approval_rate": rate(sum(trial.approval_outcome == "APPROVED" for trial in approvals), len(approvals)),
        "automation_rate": rate(sum(trial.execution_success is True and trial.verification_success is True for trial in eligible), len(eligible)),
        "unsafe_action_rate": rate(sum(trial.unsafe_executions for trial in valid), sum(trial.unsafe_action_attempts for trial in valid)),
    }


def compare(baseline: dict[str, float | int | None], opspilot: dict[str, float | int | None], metric: str) -> dict[str, float | None]:
    before = baseline.get(metric)
    after = opspilot.get(metric)
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
        return {"baseline": before, "opspilot": after, "difference": None, "relative_change_percent": None}
    difference = before - after
    return {"baseline": before, "opspilot": after, "difference": difference,
            "relative_change_percent": difference / before * 100 if before else None}
