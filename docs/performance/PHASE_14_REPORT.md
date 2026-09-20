# OpsPilot Phase 14 Performance Report

Status: local read-only measurements recorded; no capacity claim is made.

## Method

The read-only async harness in `performance/load_test.py` records request count,
success/error counts, throughput, average latency, P50, P90, P95, P99, max
latency, error types, configuration, and machine information. The dependency
probe records API, Redis, Celery, and Qdrant availability and probe latency.
Raw results belong in `performance/results/` and are intentionally not checked
in.

## Environment

- Date: 2026-09-09 (local execution)
- Host hardware: Not recorded beyond harness platform metadata
- API revision: Not recorded yet
- PostgreSQL: API readiness returned HTTP 200; direct database latency not measured
- Redis: Not measured; Python Redis client unavailable in the active interpreter
- Celery worker count: Not measured; Python Celery client unavailable in the active interpreter
- Qdrant: Root HTTP probe returned HTTP 200
- AI provider mode: Not measured yet
- Simulator configuration: Not measured yet

## Executed profiles

| Profile | Users | Spawn rate | Duration | Result |
| --- | ---: | ---: | ---: | --- |
| A | 100 | 10/s | 5 seconds | Executed against `/health/live` only |
| B | 500 | 25/s | Not measured | Not measured |
| C | 1000 | 50/s | Not measured | Not measured |

These are configured targets, not claims that the local environment can sustain
those profiles.

## Measurements

### Local profile A: `/health/live`

Raw output: `performance/results/load-profile-a-local.json`.

| Requests | Successes | Errors | Throughput | Average | P50 | P90 | P95 | P99 | Max |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,059 | 1,059 | 0 | 97.423 req/s | 82.897 ms | 33.015 ms | 225.583 ms | 331.120 ms | 510.540 ms | 701.145 ms |

This is an observed local result for a single unauthenticated liveness
endpoint. It is not representative of authenticated database-backed APIs and
is not a system capacity limit.

### Local dependency probe

Raw output: `performance/results/dependencies-local.json`.

- API liveness: available, HTTP 200, observed probe latency 3,451.753 ms.
- API readiness: available, HTTP 200, observed probe latency 2,574.882 ms.
- Qdrant root probe: available, HTTP 200, observed probe latency 1,118.315 ms.
- Redis: not measured because the active Python environment lacks the `redis` module.
- Celery: not measured because the active Python environment lacks the `celery` module.

| Area | Result |
| --- | --- |
| API latency and throughput | Liveness-only profile A measured above; authenticated/read API mix not measured |
| PostgreSQL query/pool behavior | Not measured |
| Redis latency | Not measured |
| Celery queue/task latency | Not measured |
| AI investigation latency | Not measured |
| RAG/Qdrant latency | Not measured |
| ToolGateway latency | Not measured |
| PolicyEngine latency | Not measured |
| Verification latency | Not measured |
| End-to-end recovery latency | Not measured |
| Stress/spike/soak | Not measured |
| Resource utilization | Not measured |

## Resilience

No services were stopped automatically. Destructive dependency-failure runs
require an isolated Compose environment and explicit operator execution. The
controlled scenarios and expected observations are documented in
`performance/README.md`.

## Bottlenecks and optimization

No production bottleneck or optimization claim is made. The corrected profile A
liveness run observed a P99 of 510.540 ms and max of 701.145 ms, but this endpoint-only
sample is insufficient to identify a bottleneck.

## Reproduction

```powershell
python performance/dependency_probe.py
python performance/load_test.py --profile A --host http://localhost:8000 --duration 30
python performance/load_test.py --users 25 --duration 30 --path /health/live
```

Run profiles against a dedicated environment only. Replace every `Not measured`
entry with an output-backed result; do not infer values from source code or test
counts.
