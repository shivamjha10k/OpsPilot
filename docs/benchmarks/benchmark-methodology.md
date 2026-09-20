# Phase 15 Benchmark Methodology

Phase 15 compares a recorded manual-equivalent baseline with the real OpsPilot
workflow under the same deterministic simulator scenario, seed, recovery
criteria, and isolated environment. It does not use historical numbers or
assign artificial timestamps.

## Framework

- `backend/app/benchmarks/models.py` defines configurations, ground truth,
  trial status, timestamps, and raw trial serialization.
- `backend/app/benchmarks/metrics.py` defines timestamp formulas, descriptive
  statistics, outcome rates, and baseline/OpsPilot comparisons.
- `backend/app/benchmarks/evaluation.py` defines root-cause, remediation, and
  RAG evaluation.
- `backend/app/benchmarks/catalog.py` loads the actual simulator scenario file.
- `backend/app/benchmarks/adapter.py` defines the integration boundary for a
  real baseline or OpsPilot workflow and handles warm-up, deterministic seeds,
  cooldown, and failed-trial preservation.
- `scripts/benchmarks/run_benchmark.py` creates a scenario plan or aggregates
  raw records produced by a real execution adapter.

The framework deliberately does not duplicate simulator, policy, approval,
ToolGateway, orchestration, or verification logic. An execution adapter must
invoke those existing components and record their persisted timestamps and
outcomes into `TrialResult`.

## Metric definitions

- `MTTD = detected_at - trigger_at`
- `MTTI = diagnosed_at - detected_at`
- `MTTR = resolved_at - trigger_at`
- root-cause accuracy is correct accepted causes divided by valid labeled trials;
- recommendation accuracy is an accepted registered action divided by valid
  labeled trials;
- remediation success requires both execution and verification success;
- unsafe action rate is unsafe executions divided by unsafe action attempts;
- approval rate is approved requests divided by completed approval decisions;
- automation rate is successfully executed and verified eligible actions divided
  by eligible remediation incidents.

Missing timestamps produce unavailable metrics. Invalid and failed trials remain
in the raw result and are reported; they are never silently discarded.

## Ground truth

The six current simulator scenarios are loaded from
`backend/app/simulator/scenarios.py`: high CPU, error spike, database
connection exhaustion, queue backlog, memory leak, and failed deployment. Their
trigger, root cause, evidence, action, risk, and recovery conditions become the
benchmark labels.

## Baseline

The baseline must be a recorded manual-equivalent workflow with the same
scenario and verification criteria. It may be scripted for reproducibility, but
it must be labeled as scripted manual-equivalent behavior. It must execute the
same simulator action and record actual checkpoint timestamps; it must not write
arbitrary elapsed values.

## OpsPilot

The primary OpsPilot adapter must preserve event ingestion, incident
correlation, investigation, RAG, PolicyEngine, approval, ToolGateway,
RemediationOrchestrator, and VerificationEngine. High-risk approval remains
human-gated. No benchmark flag may bypass a safety control.

## Commands

Create a plan from the real scenario catalog:

```powershell
python scripts/benchmarks/run_benchmark.py --mode catalog --trials 10
```

Aggregate actual adapter output:

```powershell
python scripts/benchmarks/run_benchmark.py --mode aggregate --input path/to/raw-trials.json --output docs/benchmarks/results
```

The input must contain a `trials` array using the serialized `TrialResult`
shape. The aggregator creates JSON and Markdown under the requested output
directory. It does not create trial records itself and will not produce
performance claims without supplied measurements.

## Reproducibility and limitations

Run against a dedicated PostgreSQL/Redis/Celery/Qdrant environment. Record
software version, seed, worker count, AI provider mode, trial count, warm-up,
cooldown, and machine metadata. Results are local, simulated, and descriptive;
they are not production capacity or statistically significant claims unless a
later study supplies sufficient repeated trials.