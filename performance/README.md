# Phase 14 Performance and Resilience Harness

This harness measures the existing system without changing application behavior. It is intentionally read-only by default and does not invoke remediation, simulator mutation, policy changes, approvals, or incident writes.

## Load profiles

Profiles are targets, not capacity claims:

- `A`: 100 concurrent users, spawn rate 10/s
- `B`: 500 concurrent users, spawn rate 25/s
- `C`: 1000 concurrent users, spawn rate 50/s

Run from the repository root:

```powershell
python performance/load_test.py --profile A --host http://localhost:8000 --duration 30
python performance/load_test.py --users 25 --spawn-rate 10 --duration 15 --path /health/live
```

Authenticated read-only traffic can be measured with a token supplied outside the repository:

```powershell
$env:OPSPILOT_TOKEN = '<access-token>'
python performance/load_test.py --users 25 --duration 30 --path /api/v1/incidents
```

Repeat `--path` to create a mixed read workload. Do not include write or remediation routes in an unreviewed load run.

Each run writes raw JSON under `performance/results/`, which is ignored by git. Results include request count, successes, errors, throughput, average latency, P50/P90/P95/P99, max latency, errors by type, configuration, and machine information.

## Dependency probes

```powershell
python performance/dependency_probe.py
```

The probe performs non-mutating checks against API liveness/readiness, Qdrant health, Redis `PING`, and Celery worker inspection. An unavailable dependency produces a measured unavailable result and a nonzero exit code; it is not treated as a passing measurement.

## Dedicated environment

Do not run performance tests against a normal developer or production-like database. Use a dedicated Compose project/environment and a separate PostgreSQL database. Keep `TEST_DATABASE_URL` and any performance database credentials outside committed files. The application remains PostgreSQL-authoritative; Redis and Celery are measured as infrastructure dependencies, not sources of truth.

For a realistic authenticated run, seed only controlled development users in the dedicated environment. The harness does not create accounts or mutate data.

## Failure and resilience plan

Controlled failure scenarios should be run separately from load profiles:

- stop PostgreSQL and record `/health/ready` plus API error behavior;
- stop Redis and record readiness, queue submission, and worker health;
- stop Celery workers and record queue/worker behavior;
- configure the mock AI provider to timeout/fail and verify investigation state;
- stop Qdrant and verify degraded RAG behavior;
- inject simulator/ToolGateway/verification failures through existing test doubles.

These scenarios are not run automatically by the harness because stopping services is destructive to the local environment and could affect unrelated work.
