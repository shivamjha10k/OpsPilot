# OpsPilot

OpsPilot is an AI-powered incident intelligence and controlled remediation platform.

## Phase 1 foundation

The current foundation provides:

- FastAPI application with OpenAPI documentation
- typed environment settings
- structured baseline logging
- PostgreSQL and Redis adapters
- liveness and dependency readiness endpoints
- Alembic migration scaffolding
- Docker Compose services for PostgreSQL, Redis, Qdrant, API, and Celery worker
- Argon2 password hashing, JWT access/refresh tokens, and server-side RBAC

## Run locally

Copy `.env.example` to `.env`, replace the local placeholder values, then start
the infrastructure:

```bash
cp .env.example .env
docker compose up --build
```

Compose requires `POSTGRES_*`, `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, and
`JWT_SECRET` from `.env`. The example file contains placeholders only. Never
commit `.env` or reuse development values in production.

The API is available at `http://localhost:8000`.

- `GET /health/live` checks process liveness
- `GET /health/ready` checks PostgreSQL and Redis connectivity
- `/docs` contains the generated API documentation

## Operations console

Phase 12 adds a React operations console under `frontend/`. It uses the
existing authenticated API and does not contain database access, simulator
mutations, policy decisions, or fabricated analytics.

Run it locally:

```bash
cd frontend
npm install
npm run dev
```

The console is available at `http://localhost:5173`. Set
`VITE_API_BASE_URL` in `frontend/.env` when the API is not running at
`http://localhost:8000`.

Available console routes include `/`, `/incidents`, `/incidents/:id`,
`/approvals`, `/services`, `/simulator`, and `/policies`. Policy management
and remediation controls remain guarded by the backend RBAC rules; the UI
only mirrors those permissions for a clearer operator experience.

## Authentication

Set `DEV_ADMIN_PASSWORD`, `DEV_ENGINEER_PASSWORD`, and `DEV_VIEWER_PASSWORD`
in `.env` before running the development seed from the repository root after
the database is running:

```bash
docker compose run --rm --no-deps backend python /opt/opspilot-scripts/seed_dev.py
```

The seed accounts are development-only and are controlled by the `DEV_*` environment variables. Never use them in production.

Authentication endpoints are under `/api/v1/auth`:

- `POST /login`
- `POST /refresh`
- `POST /logout`
- `GET /me`

Access tokens are short-lived JWTs. Refresh tokens are stateless in Phase 2 and are validated by signature, type, expiry, subject, and user activity. Logout asks the client to discard tokens; server-side revocation and refresh rotation require the later token-state infrastructure phase.

Roles are `ADMIN`, `ENGINEER`, and `VIEWER`. Authorization is enforced server-side through reusable dependencies; client-supplied roles and user IDs are never trusted.

## Phase 3 database

Phase 3 adds the PostgreSQL core domain schema: services, events, alerts, incidents, logs, metrics, deployments, runbooks, investigations, remediation records, approvals, policies, audit logs, notifications, and the incident-alert association table. PostgreSQL remains the source of truth; Redis, Celery, AI, RAG, and execution workflows are not part of this phase.

Apply migrations with:

```bash
docker compose run --rm --no-deps backend alembic upgrade head
docker compose run --rm --no-deps backend python /opt/opspilot-scripts/seed_dev.py
```

The seed creates three development users, five services, and five active runbooks. It is development-only and idempotent.

All persisted timestamps are timezone-aware UTC values. Logs and metrics use PostgreSQL `BIGINT` identity keys; normal domain entities use UUIDs. Repository integration tests use a separate `TEST_DATABASE_URL` database and never the development database.

## Phase 13 validation

The test pyramid and safety-boundary notes live in [docs/testing/README.md](docs/testing/README.md).
From `backend/`, run fast checks first and keep integration tests pointed at a
dedicated PostgreSQL database:

```bash
pytest -m unit
pytest -m security
pytest -m integration
pytest
pytest --cov=app --cov-report=term-missing
```

Frontend validation currently uses the TypeScript/Vite production build:

```bash
cd frontend
npm run build
```

Coverage and test results must be reported only from commands that actually
executed in the configured environment.

## Phase 15 benchmark evaluation

Phase 15 adds a reproducible benchmark model and aggregator under
`backend/app/benchmarks/` with its CLI in
`scripts/benchmarks/run_benchmark.py`. It loads the actual simulator scenario
catalog, defines MTTD/MTTI/MTTR and safety metrics, and compares only recorded
baseline/OpsPilot trials. A catalog plan can be generated without claiming any
measurements:

```bash
python scripts/benchmarks/run_benchmark.py --mode catalog --trials 10
```

Actual execution adapters must record real timestamps and outcomes before
aggregation. See [docs/benchmarks/benchmark-methodology.md](docs/benchmarks/benchmark-methodology.md).

## Phase 14 performance validation

The read-only performance harness and dependency probes are documented in
[performance/README.md](performance/README.md). Run them only against a
dedicated local or staging-style environment:

```bash
python performance/dependency_probe.py
python performance/load_test.py --profile A --host http://localhost:8000 --duration 30
```

Profiles A, B, and C target 100, 500, and 1000 concurrent users respectively;
they are not capacity claims. Raw results are written to the ignored
`performance/results/` directory. The report at
[docs/performance/PHASE_14_REPORT.md](docs/performance/PHASE_14_REPORT.md)
contains `Not measured` placeholders until commands are actually run.

## Development checks

From `backend/`:

```bash
pip install -r requirements-dev.txt
pytest
alembic upgrade head
```

Development credentials and secrets must be supplied through environment variables. Do not commit `.env`.

## Finalization and readiness

Final operational documentation is in [docs/operations/runbook.md](docs/operations/runbook.md)
and [docs/operations/troubleshooting.md](docs/operations/troubleshooting.md).
The demo flow is in [docs/demo.md](docs/demo.md), the final test matrix is in
[docs/testing/final-test-matrix.md](docs/testing/final-test-matrix.md), and the
evidence-based readiness classification is in
[docs/FINAL_READINESS.md](docs/FINAL_READINESS.md).

Current classification: **ready for controlled local end-to-end validation and
demo preparation; not production-ready**. The backend full suite and live
integration stack still require a provisioned declared environment.

## Phase 6 Redis and Celery Infrastructure

Redis is the Celery broker and result backend; PostgreSQL remains the source of
truth for events, alerts, incidents, users, and audit records. `POST /events`
now persists an event, marks it `QUEUED`, submits only its `event_id`, and
returns `202 Accepted`. The worker loads the event from PostgreSQL and calls
the existing `IncidentEngine`; business logic is not duplicated in Celery.

Event processing states are persisted in PostgreSQL:

```text
PERSISTED -> QUEUED -> PROCESSING -> PROCESSED
                          \-> FAILED
```

If Redis is unavailable after persistence, the API returns `503`, marks the
event `FAILED`, and preserves it for service-level reprocessing. This is not a
transactional outbox yet; the database/broker consistency window is documented
and an outbox can be added later without changing the domain layer.

Celery uses JSON-only serialization, late acknowledgements,
`task_reject_on_worker_lost`, prefetch `1`, configurable concurrency, and
bounded exponential retry with jitter for transient failures. Permanent domain
errors are recorded as `FAILED` and are not retried.

Docker development commands:

```bash
docker compose up --build -d
docker compose run --rm --no-deps backend alembic upgrade head
docker compose run --rm --no-deps backend python /opt/opspilot-scripts/seed_dev.py
```

The worker command is:

```bash
celery -A app.workers.celery_app:celery_app worker --loglevel=INFO
```

`GET /health/worker` performs a real Celery ping. It remains separate from
`/health/live` and `/health/ready`; liveness does not require dependencies,
while readiness checks PostgreSQL and Redis.

## Phase 7 AI Investigation

Phase 7 adds a provider-neutral, read-only investigation pipeline. The default
provider is deterministic `MockAIProvider`, so development and tests require no
AI credentials.

```text
Incident -> Context Builder -> Read-Only Tools -> Investigation Agent
         -> AI Provider -> Structured/Evidence Validation -> Risk Validation
         -> PostgreSQL -> Human-readable Recommendation
```

The context builder uses bounded PostgreSQL queries for service health,
metrics, logs, events, deployments, alerts, and incident history. Tool inputs
are strict Pydantic models and the registry contains no mutation, shell, URL,
or arbitrary SQL tool. Operational text is untrusted data. Secrets and prompts
are not exposed by the investigation API.

`POST /api/v1/incidents/{id}/investigate` is restricted to engineers/admins and
returns `202 Accepted`; repeated requests reuse a pending/running investigation.
`GET /api/v1/investigations/{id}` is available to authenticated users. Results
are persisted in the existing `ai_investigations` table with explicit lifecycle
status, validated evidence, confidence, deterministic minimum risk, prompt
version, duration, and audit events. Recommendations are data only: Phase 7
does not execute remediation or implement RAG, embeddings, or Qdrant retrieval.

## Phase 8 RAG Knowledge Layer

Phase 8 adds Qdrant as a derived semantic index while PostgreSQL remains the
source of truth. The default `MockEmbeddingProvider` is deterministic and
offline, using the configured `EMBEDDING_DIMENSION` (64 by default). The
initial collection is `opspilot_knowledge`; changing the embedding model or
dimension requires an explicit rebuild.

```text
Source Documents -> Clean/Normalize -> Section-aware Chunker
                 -> Embedding Provider -> Qdrant
                 -> Bounded Retriever -> AI Investigation
```

Active runbooks, sufficiently complete incidents, and active
`knowledge_documents` can be indexed. Each chunk has bounded content,
document type, source identity, version/timestamps, section, embedding model,
and a deterministic UUID point ID. Reindexing deletes existing points for the
source before upserting new chunks.

Retrieval supports service, environment, and document-type filters with
bounded fallback broadening, configurable `RAG_TOP_K`, result limits, scores,
and source references in the form `document_id:chunk_id`. Retrieved knowledge
is explicitly untrusted reference data, separate from agent instructions, and
cannot execute commands. Citations are validated before an investigation stores
them.

Indexing is asynchronous through `opspilot.index_runbook`,
`opspilot.index_incident`, `opspilot.reindex_document`, and the explicit
`opspilot.rebuild_knowledge_index` task. Engineers/admins can queue a runbook
with `POST /api/v1/runbooks/{id}/index`; `GET /health/qdrant` reports Qdrant
availability. Qdrant or embedding failures never delete PostgreSQL sources.

## Phase 9 Controlled Tool Gateway

Phase 9 adds the only controlled execution boundary for remediation. The
gateway has an explicit registry containing exactly five simulator tools:
`restart_service`, `scale_service`, `rollback_deployment`, `clear_cache`, and
`scale_workers`. Every request passes strict Pydantic input validation,
Engineer/Admin authorization, incident/service environment checks, authoritative
registry risk metadata, idempotency handling, PostgreSQL persistence, audit
logging, and (for low-risk actions) a Celery task before reaching the simulator.

The simulator persists service state in PostgreSQL, including replicas,
workers, cache generation, deployment version, metrics, and lifecycle state.
It never invokes shell commands, SQL supplied by users, HTTP/cloud APIs,
Docker/Kubernetes/SSH, Redis flushes, arbitrary code, or real infrastructure.
Low-risk actions execute in the simulator; medium/high-risk actions are stored
as `APPROVAL_REQUIRED` and do not execute without approval. Critical or
unregistered tools are rejected. Tool execution records structured
success/failure results, timeouts, and audit events, and never resolves or
mutates incident lifecycle.

The Phase 9 endpoints are:

* `GET /api/v1/incidents/{id}/remediation/recommendations`
* `POST /api/v1/incidents/{id}/remediation`
* `GET /api/v1/remediation/{action_id}`

## Phase 10 Policy and Human Approval

Policy evaluation is deterministic and defaults to deny. The registry remains
authoritative for tool risk and environment support; critical-risk actions,
unknown actions/environments, inactive callers, and missing policies cannot
execute. Policies are managed by admins through `GET /api/v1/policies`,
`POST /api/v1/policies`, and `PATCH /api/v1/policies/{id}`.

Actions requiring approval create a pending approval bound to the exact
incident, parameters, environment, effective risk, requester, and policy
snapshot. Approval is time-limited, auditable, and cannot be self-approved by
the requester for high-risk actions. The gateway re-evaluates policy and the
action fingerprint immediately before execution; policy changes, changed
parameters, expired approvals, and terminal incidents block execution.

Approval routes are `GET /api/v1/approvals/pending`,
`POST /api/v1/approvals/{id}/approve`, and
`POST /api/v1/approvals/{id}/reject`. PostgreSQL remains authoritative for
policy frequency checks, approval state, remediation state, and audit records.

## Phase 11 Remediation Orchestration and Verification

Celery invokes `RemediationOrchestrator`, which re-enters the existing
ToolGateway and then invokes `VerificationEngine`. Verification reads fresh
persisted `Service.simulation_state` values rather than trusting tool success.
Recovery criteria are scenario-specific for health, CPU, memory, error rate,
latency, database connections, queue depth, worker utilization, and deployment
version. Verification requires configurable consecutive successful checks and
bounded attempts. Failed checks never resolve an incident; exhausted checks
follow `VERIFYING -> FAILED -> ESCALATED`.

Execution retries are limited by `TOOL_MAX_RETRIES`, require an idempotent
registered tool and a retryable gateway result, and repeat the policy, approval,
fingerprint, authorization, and idempotency gates. Verification history is
bounded inside `remediation_actions.result` and is exposed through
`GET /api/v1/remediation/{action_id}/verification`.

## Phase 4 Incident Engine

Phase 4 adds deterministic incident intelligence without AI, workers, Redis, or
external integrations. Operational events enter through `POST /api/v1/events`.
The application validates and stores the event, normalizes recognized failure
events into alerts, and correlates compatible alerts into incidents.

The correlation window is configured with `INCIDENT_CORRELATION_WINDOW_MINUTES`
and defaults to five minutes. Correlation requires the same service, an active
incident, a timestamp inside the window, and compatible severity/alert-type
groups. Informational and deployment events are stored without creating alerts.

Incident lifecycle transitions are centralized in `IncidentStateMachine`:

```text
DETECTED -> ACKNOWLEDGED -> INVESTIGATING -> DIAGNOSED
    -> REMEDIATION_PENDING -> APPROVAL_PENDING -> EXECUTING
    -> VERIFYING -> RESOLVED

VERIFYING -> FAILED -> ESCALATED
Any active state -> ESCALATED
```

Engineer and admin users can ingest events, create manual incidents,
acknowledge, assign, and escalate. Viewers can read events, alerts, incidents,
and timelines. Event IDs are database-unique and duplicate submissions return
the existing event without creating another alert or incident. Incident actions
are recorded in the Phase 3 `audit_logs` table and exposed through the timeline
endpoint.

Phase 4 endpoints:

- `POST /api/v1/events`
- `GET /api/v1/events`
- `GET /api/v1/alerts`
- `GET /api/v1/incidents`
- `GET /api/v1/incidents/{id}`
- `POST /api/v1/incidents`
- `POST /api/v1/incidents/{id}/acknowledge`
- `POST /api/v1/incidents/{id}/assign`
- `POST /api/v1/incidents/{id}/escalate`
- `GET /api/v1/incidents/{id}/timeline`

Event processing is committed as one database transaction. PostgreSQL unique
constraints protect event idempotency and incident numbering. Active incident
rows are locked during correlation; without distributed locking, two separate
processes can still create separate incidents when no active incident exists at
the same instant. This limitation is documented and intentionally leaves
Redis/Celery for a later phase.

## Phase 5 Production Environment Simulator

The simulator is a safe, deterministic, in-process environment for generating
operational conditions. It models payment, order, user, notification, and
search services with service-specific baselines and explicit NORMAL,
DEGRADED, FAILED, and RECOVERING state concepts. It persists important
metrics, logs, deployment records, and events through the existing domain
models.

Scenario execution is tick-driven rather than an uncontrolled background loop.
Triggering a scenario performs its first deterministic tick immediately;
additional ticks can be advanced by the application manager for tests. The
six scenarios are `high_cpu`, `error_spike`, `db_connection_exhaustion`,
`queue_backlog`, `memory_leak`, and `failed_deployment`.

Simulator routes:

- `GET /api/v1/simulator/services`
- `GET /api/v1/simulator/scenarios`
- `POST /api/v1/simulator/scenarios/{scenario}/trigger`
- `POST /api/v1/simulator/simulations/{id}/stop`
- `GET /api/v1/simulator/simulations/{id}`
- `GET /api/v1/simulator/simulations`

Viewer users can inspect simulator state. Engineers and admins can trigger and
stop scenarios. The simulator never writes incidents directly: generated
events call the Phase 4 event ingestion service, which creates alerts and
incidents. Stopping a simulation preserves telemetry and leaves incident state
unchanged. The simulator cannot execute shell commands, infrastructure
operations, remediation, rollback, or recovery actions.

Simulator settings are development-oriented and configurable with
`SIMULATOR_ENABLED`, `SIMULATOR_TICK_INTERVAL_SECONDS`, and
`SIMULATOR_RANDOM_SEED`. The `simulation_runs` table stores execution control
metadata; transient service state remains bounded in memory.
