from datetime import datetime, timedelta, timezone

import pytest

from app.benchmarks.evaluation import evaluate_rag, evaluate_recommendation, evaluate_root_cause
from app.benchmarks.catalog import load_ground_truth
from app.benchmarks.metrics import compare, outcome_summary, summarize_trials, timestamp_metrics
from app.benchmarks.models import ScenarioGroundTruth, TrialResult, TrialStatus


def truth() -> ScenarioGroundTruth:
    return ScenarioGroundTruth(
        scenario="test", trigger_condition="signal", expected_root_cause="CPU saturation",
        acceptable_root_causes=frozenset({"CPU saturation", "resource exhaustion"}),
        expected_evidence=("cpu",), expected_action="restart_service",
        acceptable_actions=frozenset({"restart_service"}), expected_risk_level="MEDIUM",
        recovery_conditions=("CPU below threshold",),
    )


def valid_trial(mode: str = "OPSPILOT") -> TrialResult:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    trial = TrialResult(
        scenario="test", seed=7, mode=mode, status=TrialStatus.VALID,
        timestamps={"trigger_at": start, "detected_at": start + timedelta(seconds=2),
                    "diagnosed_at": start + timedelta(seconds=8), "resolved_at": start + timedelta(seconds=20)},
        root_cause="CPU saturation", recommendation_action="restart_service",
        execution_success=True, verification_success=True, automation_eligible=True,
        unsafe_action_attempts=2, unsafe_executions=0,
    )
    return trial


def test_timestamp_definitions_and_statistics() -> None:
    trial = valid_trial()
    assert timestamp_metrics(trial)["mttd_seconds"] == 2
    assert timestamp_metrics(trial)["mtti_seconds"] == 6
    assert timestamp_metrics(trial)["mttr_seconds"] == 20
    assert summarize_trials([trial], "mttr_seconds")["mean"] == 20


def test_invalid_trial_is_excluded_but_counted() -> None:
    trial = valid_trial()
    trial.status = TrialStatus.INVALID
    trial.failure_reason = "missing verification timestamp"
    assert summarize_trials([trial], "mttr_seconds")["count"] == 0
    assert outcome_summary([trial])["invalid_trials"] == 1


def test_evaluation_and_rag_metrics_are_grounded() -> None:
    trial = valid_trial()
    assert evaluate_root_cause(trial, truth()) is True
    assert evaluate_recommendation(trial, truth()) == "CORRECT"
    assert evaluate_rag({"doc-a", "doc-b"}, ["doc-x", "doc-b"], 2)["recall_at_k"] == 0.5


def test_comparison_does_not_divide_by_zero() -> None:
    result = compare({"mean": 0}, {"mean": 1}, "mean")
    assert result["relative_change_percent"] is None


def test_naive_timestamp_is_rejected() -> None:
    trial = valid_trial()
    trial.timestamps["trigger_at"] = datetime(2026, 1, 1)
    with pytest.raises(ValueError, match="timezone"):
        trial.validate()


def test_ground_truth_comes_from_all_simulator_scenarios() -> None:
    catalog = load_ground_truth()
    assert set(catalog) == {
        "high_cpu", "error_spike", "db_connection_exhaustion", "queue_backlog", "memory_leak", "failed_deployment",
    }
    assert catalog["db_connection_exhaustion"].acceptable_actions == frozenset({"rollback_deployment", "scale_service"})
    assert catalog["failed_deployment"].acceptable_actions == frozenset({"rollback_deployment"})

def test_evaluate_root_cause_substring() -> None:
    trial = valid_trial()
    trial.root_cause = "CPU saturation threshold exceeded."
    assert evaluate_root_cause(trial, truth()) is True
    
    trial.root_cause = "Unrelated issue"
    assert evaluate_root_cause(trial, truth()) is False

def test_recommendation_accuracy_excludes_missing() -> None:
    from app.benchmarks.evaluation import evaluate_recommendation
    from scripts.benchmarks.run_benchmark import _recommendation_accuracy
    
    trial1 = valid_trial()
    trial1.recommendation_action = "restart_service"  # Correct
    
    trial2 = valid_trial()
    trial2.recommendation_action = "unknown_action"  # Incorrect
    
    trial3 = valid_trial(mode="BASELINE")
    trial3.recommendation_action = None  # Missing
    
    catalog = {"test": truth()}
    
    # Accuracy should only count trial1 and trial2 (1 correct out of 2) -> 0.5
    assert _recommendation_accuracy([trial1, trial2, trial3], catalog) == 0.5
    
    # If all trials are missing, should return None
    assert _recommendation_accuracy([trial3], catalog) is None