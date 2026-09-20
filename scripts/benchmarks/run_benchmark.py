"""Phase 15 benchmark planner and result aggregator.

This command never fabricates workflow timestamps. `catalog` creates a plan from
actual simulator scenarios. `aggregate` consumes trial JSON produced by a real
baseline/OpsPilot adapter and generates machine-readable and Markdown output.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.benchmarks.catalog import load_ground_truth
from app.benchmarks.evaluation import accuracy, evaluate_rag, evaluate_recommendation, evaluate_root_cause
from app.benchmarks.metrics import compare, outcome_summary, summarize_trials, timestamp_metrics
from app.benchmarks.models import BenchmarkConfig, BenchmarkRun, TrialResult, TrialStatus


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan or aggregate OpsPilot Phase 15 benchmarks")
    parser.add_argument("--mode", choices=("catalog", "aggregate"), default="catalog")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260909)
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--cooldown", type=float, default=0)
    parser.add_argument("--input", type=Path, help="Raw trial JSON for aggregate mode")
    parser.add_argument("--output", type=Path, default=Path("docs/benchmarks/results"))
    return parser.parse_args()


def config_from_args(args: argparse.Namespace, scenarios: tuple[str, ...]) -> BenchmarkConfig:
    return BenchmarkConfig(scenarios=scenarios, trials=args.trials, seed=args.seed,
                           warmup=args.warmup, cooldown_seconds=args.cooldown)


def scenario_plan(config: BenchmarkConfig) -> dict[str, Any]:
    catalog = load_ground_truth()
    unknown = sorted(set(config.scenarios) - set(catalog))
    if unknown:
        raise ValueError(f"unknown scenarios: {', '.join(unknown)}")
    return {
        "benchmark_version": config.benchmark_version,
        "configuration": {"scenarios": list(config.scenarios), "trials": config.trials, "seed": config.seed,
                           "warmup": config.warmup, "cooldown_seconds": config.cooldown_seconds},
        "methodology": {
            "baseline": "A recorded manual-equivalent workflow using the same seeded scenario and recovery criteria.",
            "opspilot": "The real API/AI/RAG/policy/approval/ToolGateway/orchestration/verification path.",
            "mttd": "detected_at - trigger_at",
            "mtti": "diagnosed_at - detected_at",
            "mttr": "resolved_at - trigger_at",
            "valid_trial": "All required timestamps and persisted outcomes exist and are chronological.",
        },
        "scenarios": [{"scenario": catalog[name].scenario, "trigger_condition": catalog[name].trigger_condition,
                       "expected_root_cause": catalog[name].expected_root_cause,
                       "acceptable_root_causes": sorted(catalog[name].acceptable_root_causes),
                       "expected_evidence": list(catalog[name].expected_evidence),
                       "expected_action": catalog[name].expected_action,
                       "acceptable_actions": sorted(catalog[name].acceptable_actions),
                       "expected_risk_level": catalog[name].expected_risk_level,
                       "recovery_conditions": list(catalog[name].recovery_conditions)} for name in config.scenarios],
        "status": "PLAN_ONLY_NO_MEASUREMENTS",
    }


def parse_trial(raw: dict[str, Any]) -> TrialResult:
    timestamps = {key: datetime.fromisoformat(value) if value else None for key, value in raw.get("timestamps", {}).items()}
    trial = TrialResult(
        scenario=raw["scenario"], seed=int(raw["seed"]), trial_id=raw.get("trial_id", str(uuid.uuid4())),
        mode=raw.get("mode", "OPSPILOT"), status=TrialStatus(raw.get("status", "FAILED")),
        failure_reason=raw.get("failure_reason"), timestamps=timestamps,
        root_cause=raw.get("root_cause"), recommendation_action=raw.get("recommendation_action"),
        risk_level=raw.get("risk_level"), rag_relevant_documents=set(raw.get("rag_relevant_documents", [])),
        rag_retrieved_documents=list(raw.get("rag_retrieved_documents", [])),
        automation_eligible=bool(raw.get("automation_eligible", False)), approval_outcome=raw.get("approval_outcome"),
        execution_success=raw.get("execution_success"), verification_success=raw.get("verification_success"),
        unsafe_action_attempts=int(raw.get("unsafe_action_attempts", 0)),
        unsafe_executions=int(raw.get("unsafe_executions", 0)), metrics=raw.get("metrics", {}),
    )
    trial.validate()
    return trial


def aggregate(input_path: Path, output_dir: Path, args: argparse.Namespace) -> tuple[Path, Path]:
    if not input_path.exists():
        raise SystemExit(
            f"benchmark input does not exist: {input_path}\n"
            "Run a real baseline/OpsPilot adapter first, then pass its JSON file with --input."
        )
    if not input_path.is_file():
        raise SystemExit(f"benchmark input is not a file: {input_path}")
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"benchmark input is not valid UTF-8 JSON: {input_path} ({exc})") from exc
    if not isinstance(payload, (list, dict)):
        raise SystemExit("benchmark input root must be a JSON object with 'trials' or a JSON trial array")
    raw_trials = payload if isinstance(payload, list) else payload.get("trials", [])
    if not isinstance(raw_trials, list):
        raise SystemExit("benchmark input must contain a JSON array named 'trials'")
    if not raw_trials:
        raise SystemExit("benchmark input contains no trials; no benchmark report was generated")
    trials = [parse_trial(item) for item in raw_trials]
    scenarios = tuple(sorted({trial.scenario for trial in trials}))
    config = config_from_args(args, scenarios)
    run = BenchmarkRun(str(uuid.uuid4()), datetime.now(timezone.utc), config, trials,
                       {"platform": platform.platform(), "python": sys.version})
    catalog = load_ground_truth()
    unknown = sorted(set(scenarios) - set(catalog))
    if unknown:
        raise SystemExit(f"benchmark input contains unknown scenarios: {', '.join(unknown)}")
    summaries: dict[str, Any] = {}
    comparisons: dict[str, Any] = {}
    for mode in sorted({trial.mode for trial in trials}):
        mode_trials = [trial for trial in trials if trial.mode == mode]
        summaries[mode] = {"outcomes": outcome_summary(mode_trials),
                           "mttd": summarize_trials(mode_trials, "mttd_seconds"),
                           "mtti": summarize_trials(mode_trials, "mtti_seconds"),
                           "mttr": summarize_trials(mode_trials, "mttr_seconds"),
                           "root_cause_accuracy": accuracy(evaluate_root_cause(trial, catalog[trial.scenario])
                                                             for trial in mode_trials if trial.status is TrialStatus.VALID),
                           "recommendation_accuracy": _recommendation_accuracy(mode_trials, catalog),
                           "rag": _rag_summary(mode_trials),}
    if "BASELINE" in summaries and "OPSPILOT" in summaries:
        for metric in ("mttd", "mtti", "mttr"):
            comparisons[metric] = compare(summaries["BASELINE"][metric], summaries["OPSPILOT"][metric], "mean")
    result = run.to_dict() | {"summary": summaries, "comparison": comparisons}
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{run.benchmark_run_id}.json"
    md_path = output_dir / f"{run.benchmark_run_id}.md"
    json_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, md_path


def _recommendation_accuracy(trials: list[TrialResult], catalog: dict) -> float | None:
    applicable = [trial for trial in trials if trial.status is TrialStatus.VALID and trial.recommendation_action is not None]
    if not applicable:
        return None
    values = [evaluate_recommendation(trial, catalog[trial.scenario]) == "CORRECT" for trial in applicable]
    return sum(values) / len(values) if values else 0.0


def _rag_summary(trials: list[TrialResult]) -> dict[str, Any]:
    values = [evaluate_rag(trial.rag_relevant_documents, trial.rag_retrieved_documents, 5) for trial in trials if trial.status is TrialStatus.VALID]
    return {"queries": len(values), "hit_at_5": sum(item["hit_at_k"] for item in values) / len(values) if values else None,
            "recall_at_5": sum(item["recall_at_k"] for item in values if item["recall_at_k"] is not None) / len(values) if values else None}


def render_markdown(result: dict[str, Any]) -> str:
    lines = [f"# Benchmark Run {result['benchmark_run_id']}", "", "LOCAL BENCHMARK / SIMULATED ENVIRONMENT", "",
             "No value in this report is inferred from source code; values come from supplied trial records.", "",
             "## Summary", "", "| Mode | Trials | MTTD mean (s) | MTTI mean (s) | MTTR mean (s) | Root cause accuracy | Recommendation accuracy |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for mode, summary in result.get("summary", {}).items():
        lines.append(f"| {mode} | {summary['outcomes']['valid_trials']} | {_value(summary['mttd']['mean'])} | {_value(summary['mtti']['mean'])} | {_value(summary['mttr']['mean'])} | {_value(summary['root_cause_accuracy'])} | {_value(summary['recommendation_accuracy'])} |")
    lines.extend(["", "## Comparison", "", "| Metric | Baseline | OpsPilot | Difference | Relative change |", "| --- | ---: | ---: | ---: | ---: |"])
    for metric, values in result.get("comparison", {}).items():
        lines.append(f"| {metric} | {_value(values.get('baseline'))} | {_value(values.get('opspilot'))} | {_value(values.get('difference'))} | {_value(values.get('relative_change_percent'))}% |")
    lines.extend(["", "## Limitations", "", "Trials marked INVALID or FAILED remain in the machine-readable result. Missing timestamps produce unavailable metrics; they are not replaced with zeroes."])
    return "\n".join(lines) + "\n"


def _value(value: Any) -> str:
    return "Not measured" if value is None else f"{value:.6g}" if isinstance(value, float) else str(value)


def main() -> int:
    args = parse_args()
    catalog = load_ground_truth()
    scenarios = tuple(args.scenarios or sorted(catalog))
    config = config_from_args(args, scenarios)
    if args.mode == "catalog":
        print(json.dumps(scenario_plan(config), indent=2, default=str))
        return 0
    if args.input is None:
        raise SystemExit("aggregate mode requires --input containing actual recorded trials")
    json_path, md_path = aggregate(args.input, args.output, args)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
