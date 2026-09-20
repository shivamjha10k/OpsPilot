from __future__ import annotations

from typing import Iterable

from .models import ScenarioGroundTruth, TrialResult


def _normalize(value: str | None) -> str:
    return " ".join((value or "").lower().replace("_", " ").replace("-", " ").split())


def evaluate_root_cause(trial: TrialResult, truth: ScenarioGroundTruth) -> bool | None:
    if trial.root_cause is None:
        return None
    candidate = _normalize(trial.root_cause)
    accepted = {_normalize(item) for item in truth.acceptable_root_causes}
    expected = _normalize(truth.expected_root_cause)
    
    if candidate in accepted or candidate == expected:
        return True
        
    if expected in candidate:
        return True
        
    for item in accepted:
        if item in candidate:
            return True
            
    return False


def evaluate_recommendation(trial: TrialResult, truth: ScenarioGroundTruth) -> str:
    if not trial.recommendation_action:
        return "MISSING"
    candidate = _normalize(trial.recommendation_action)
    accepted = {_normalize(item) for item in truth.acceptable_actions}
    if candidate in accepted or candidate == _normalize(truth.expected_action):
        return "CORRECT"
    if candidate in {_normalize(truth.expected_action), _normalize(truth.expected_action.split(" or ")[0])}:
        return "PARTIAL"
    return "INCORRECT"


def evaluate_rag(relevant: set[str], retrieved: Iterable[str], k: int) -> dict[str, float | int | None]:
    if k < 1:
        raise ValueError("k must be positive")
    top = list(retrieved)[:k]
    hits = len(set(top) & relevant)
    return {
        "k": k, "relevant_count": len(relevant), "retrieved_count": len(top), "hits": hits,
        "hit_at_k": 1.0 if hits else 0.0,
        "recall_at_k": hits / len(relevant) if relevant else None,
    }


def accuracy(values: Iterable[bool | None]) -> float | None:
    observed = [value for value in values if value is not None]
    return sum(observed) / len(observed) if observed else None


def rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None
