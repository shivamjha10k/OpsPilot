from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from .models import BenchmarkConfig, TrialResult, TrialStatus


class BenchmarkAdapter(Protocol):
    """An integration boundary for a real baseline or OpsPilot workflow."""

    def run_trial(self, *, scenario: str, seed: int, trial_number: int, mode: str) -> TrialResult:
        ...


def execute_trials(config: BenchmarkConfig, adapter: BenchmarkAdapter, mode: str,
                   sleep: Callable[[float], None] = time.sleep) -> list[TrialResult]:
    """Run recorded trials through an adapter without changing application safety gates."""
    for warmup_number in range(config.warmup):
        adapter.run_trial(scenario=config.scenarios[warmup_number % len(config.scenarios)],
                          seed=config.seed + warmup_number, trial_number=warmup_number, mode=f"{mode}_WARMUP")
    trials: list[TrialResult] = []
    trial_number = 0
    for scenario in config.scenarios:
        for offset in range(config.trials):
            seed = config.seed + trial_number
            try:
                trial = adapter.run_trial(scenario=scenario, seed=seed, trial_number=offset, mode=mode)
                trial.validate()
            except Exception as exc:
                trial = TrialResult(scenario=scenario, seed=seed, mode=mode, status=TrialStatus.FAILED,
                                    failure_reason=type(exc).__name__)
            trials.append(trial)
            trial_number += 1
            if config.cooldown_seconds:
                sleep(config.cooldown_seconds)
    return trials
