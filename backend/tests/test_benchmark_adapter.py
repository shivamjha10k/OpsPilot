from app.benchmarks.adapter import execute_trials
from app.benchmarks.models import BenchmarkConfig, TrialResult, TrialStatus


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def run_trial(self, *, scenario: str, seed: int, trial_number: int, mode: str) -> TrialResult:
        self.calls.append((scenario, mode))
        return TrialResult(scenario=scenario, seed=seed, mode=mode, status=TrialStatus.INVALID,
                           failure_reason="fixture-only")


def test_adapter_runner_keeps_warmups_out_of_results_and_seeds_trials() -> None:
    adapter = FakeAdapter()
    trials = execute_trials(BenchmarkConfig(("high_cpu",), trials=2, seed=10, warmup=1), adapter, "BASELINE",
                             sleep=lambda _: None)

    assert len(trials) == 2
    assert adapter.calls == [("high_cpu", "BASELINE_WARMUP"), ("high_cpu", "BASELINE"), ("high_cpu", "BASELINE")]
    assert [trial.seed for trial in trials] == [10, 11]