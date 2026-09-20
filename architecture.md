                         ┌──────────────────────────────┐
                         │       USERS / CLIENTS        │
                         │                              │
                         │ React Web UI                 │
                         │ Engineers / SRE / Admin      │
                         │ API Clients / Integrations   │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │       NETWORK / EDGE         │
                         │                              │
                         │ Reverse Proxy               │
                         │ TLS / Routing / Rate Limits │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI APPLICATION                              │
│                                                                          │
│  ┌───────────────┐   ┌──────────────┐   ┌────────────────────────────┐  │
│  │ API LAYER     │──▶│ SERVICE      │──▶│ REPOSITORY / DATA ACCESS   │  │
│  │               │   │ LAYER        │   │                            │  │
│  │ /auth         │   │ Auth         │   │ UserRepository             │  │
│  │ /services     │   │ Incident     │   │ IncidentRepository          │  │
│  │ /incidents    │   │ AI/RAG       │   │ EventRepository             │  │
│  │ /events       │   │ Remediation  │   │ ServiceRepository            │  │
│  │ /metrics      │   │ Policy       │   │ RunbookRepository            │  │
│  │ /logs         │   │ Verification │   │ AuditRepository              │  │
│  │ /remediation  │   │ Simulator    │   │ etc.                         │  │
│  └───────────────┘   └──────────────┘   └──────────────┬─────────────┘  │
│                                                        │                │
│  ┌─────────────────────────────────────────────────────┴──────────────┐ │
│  │                    CORE / CROSS-CUTTING                           │ │
│  │ Auth • RBAC • Validation • Config • Logging • Request IDs          │ │
│  │ Error Handling • Security • Audit • Observability                  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬───────────────────────────┬──────────────┘
                                │                           │
                    ┌───────────▼──────────┐       ┌──────▼─────────────┐
                    │    ASYNC LAYER       │       │   AI / AGENT LAYER │
                    │                      │       │                    │
                    │ Redis                │       │ Context Builder    │
                    │ Celery               │       │ RAG                │
                    │ Background Workers   │       │ LLM                │
                    │ Event Processing      │       │ Agent              │
                    └───────────┬──────────┘       │ Tool Registry      │
                                │                  │ Tool Gateway       │
                                │                  └─────────┬──────────┘
                                │                            │
                                ▼                            ▼
                    ┌────────────────────┐       ┌──────────────────────┐
                    │    PostgreSQL       │       │    POLICY ENGINE     │
                    │                    │       │                      │
                    │ Users              │       │ Risk Classification  │
                    │ Services            │       │ ALLOW                │
                    │ Events              │       │ APPROVAL REQUIRED    │
                    │ Alerts              │       │ BLOCK                │
                    │ Incidents           │       └──────────┬───────────┘
                    │ Logs                │                  │
                    │ Metrics             │                  ▼
                    │ Deployments         │       ┌──────────────────────┐
                    │ Runbooks            │       │ HUMAN APPROVAL       │
                    │ Remediation         │       │                      │
                    │ Policies            │       │ Approve / Reject     │
                    │ Audit Logs          │       └──────────┬───────────┘
                    └────────────────────┘                  │
                                                            ▼
                                                  ┌──────────────────────┐
                                                  │ REMEDIATION TOOLS    │
                                                  │                      │
                                                  │ Restart              │
                                                  │ Scale                │
                                                  │ Rollback             │
                                                  │ Clear Cache          │
                                                  │ Scale Workers        │
                                                  └──────────┬───────────┘
                                                             │
                                                             ▼
                                                  ┌──────────────────────┐
                                                  │ VERIFICATION ENGINE  │
                                                  │                      │
                                                  │ Health               │
                                                  │ Error Rate           │
                                                  │ Latency              │
                                                  │ Dependencies         │
                                                  └──────────┬───────────┘
                                                             │
                                             ┌───────────────┴──────────────┐
                                             ▼                              ▼
                                      ┌─────────────┐                ┌─────────────┐
                                      │  RESOLVED   │                │ ESCALATED   │
                                      └─────────────┘                └─────────────┘



And underneath that sits our simulated production environment
             PRODUCTION SIMULATOR
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
 payment-service  order-service  user-service
       │             │             │
       ├─────────────┼─────────────┤
       ▼             ▼             ▼
    Metrics        Logs        Deployments
       │             │             │
       └─────────────┼─────────────┘
                     ▼
               Event Pipeline
                     │
                     ▼
               OpsPilot Engine




And Qdrant sits beside PostgreSQL, not as a replacement for it:

                     ┌───────────────┐
                     │   PostgreSQL  │
                     │ Source of     │
                     │ truth         │
                     └───────────────┘

                     ┌───────────────┐
                     │    Qdrant     │
                     │ Vector search │
                     │ RAG knowledge │
                     └───────────────┘
Most important security boundary

This is the part I want us to be especially strict about:

                    AI AGENT
                       │
                       ▼
               ┌──────────────┐
               │ Tool Gateway │
               └──────┬───────┘
                      │
              Validate parameters
                      │
              Check permissions
                      │
               Determine risk
                      │
              Check environment
                      │
               Check policy
                      │
             ┌────────┼────────┐
             ▼        ▼        ▼
           ALLOW   APPROVAL   BLOCK
             │        │
             │        ▼
             │     HUMAN
             │    APPROVAL
             │        │
             └────┬───┘
                  ▼
             EXECUTE TOOL
                  │
                  ▼
              VERIFY
                  │
            ┌─────┴─────┐
            ▼           ▼
         SUCCESS      FAILURE
            │           │
            ▼           ▼
        RESOLVED     ESCALATE


PHASE 2 AUTHENTICATION AND RBAC

The identity boundary is implemented inside the FastAPI application:

Client
  -> POST /api/v1/auth/login
  -> credential verification against PostgreSQL
  -> short-lived access JWT plus longer-lived refresh JWT
  -> protected request with Bearer access token
  -> signature, algorithm, expiry, token type, subject, and active-user checks
  -> reusable role dependency
  -> endpoint

The user database is authoritative. The JWT contains only the user UUID, token
type, issued-at time, expiry, and unique token identifier. Roles are read from
the server-side user record and are never accepted from a client request.

Initial roles are ADMIN, ENGINEER, and VIEWER. Authorization is centralized in
reusable dependencies so later domain routes can declare role or permission
requirements without duplicating checks in route handlers.

Passwords use Argon2id through the maintained argon2-cffi library. Plaintext
passwords and password hashes are never returned by API schemas or placed in
tokens. Email addresses are normalized before storage and lookup, while the
database enforces uniqueness.

Phase 2 refresh tokens are stateless and validated by signature, token type,
expiry, subject, and active-user state. Logout therefore asks the client to
discard its tokens; server-side revocation and rotation require later token
state infrastructure. Login brute-force protection and distributed rate
limiting are also intentionally deferred to the later Redis infrastructure
phase.


PHASE 3 CORE DOMAIN DATABASE

PostgreSQL remains the source of truth. The domain layer uses SQLAlchemy 2.x
typed mappings and keeps persistence concerns in repositories:

API -> application/service layer -> repository -> SQLAlchemy model -> PostgreSQL

The schema uses UUID primary keys for normal entities and BIGINT identity keys
for high-volume logs and metrics. Reusable enums are represented in the ORM
and protected by database-level check constraints in the migration. All
timestamps are timezone-aware and stored in UTC.

Core relationships include:

- users own services, are assigned incidents, create runbooks and policies, and are associated with deployments, remediation requests, approvals, audit records, and notifications;
- services contain events, alerts, incidents, logs, metrics, and deployments;
- incidents belong to services, may be assigned to users, connect to alerts through a composite-key association table, and own investigations and remediation records;
- remediation actions may have one approval record and retain requester/approver identity references;
- historical and audit-oriented foreign keys are restrictive or nullable with `SET NULL` where deletion must preserve history.

The Phase 3 migration is `0002_core_domain`, following the Phase 2 users
migration. Seed data is controlled, development-only, and idempotent. Repository
integration tests use a dedicated PostgreSQL test database; `Base.metadata` is
used only for isolated test setup, never as the production migration strategy.


PHASE 4 DETERMINISTIC INCIDENT ENGINE

Events are accepted by the protected event API, validated by Pydantic, stored
with a unique event_id, and processed in one database transaction. Recognized
failure events are normalized into alerts. Informational and deployment events
remain persisted events without alerts.

Alert correlation is deterministic: the same service, an active incident, a
configurable timestamp window (`INCIDENT_CORRELATION_WINDOW_MINUTES`, default
five minutes), and compatible alert type/severity groups are required. Active
incident rows are locked during correlation. The event unique constraint is the
final idempotency guard for duplicate submissions.

The incident state machine is:

    DETECTED -> ACKNOWLEDGED -> INVESTIGATING -> DIAGNOSED
        -> REMEDIATION_PENDING -> APPROVAL_PENDING -> EXECUTING
        -> VERIFYING -> RESOLVED

    VERIFYING -> FAILED -> ESCALATED
    any active state -> ESCALATED

Incident actions use the Phase 3 audit_logs table. The timeline is a
chronological projection of persisted incident audit records, including
creation, alert association, acknowledgement, assignment, escalation, and
status changes. Engineer/admin roles modify incidents; all authenticated roles
may read incidents, alerts, events, and timelines.

Phase 4 deliberately contains no AI, Redis/Celery processing, simulator,
remediation execution, policy evaluation, frontend, or WebSocket behavior.


PHASE 5 PRODUCTION ENVIRONMENT SIMULATOR

The simulator is an in-process, tick-driven source of operational signals. It
does not create incidents directly. Its flow is:

    Scenario manager -> simulated service state -> metrics/logs/deployments
        -> Event model -> Phase 4 IncidentEngine -> alerts/incidents/audit

Five services use distinct baselines: payment-service, order-service,
user-service, notification-service, and search-service. Each state contains
health/lifecycle, version, resource metrics, dependency status, and a bounded
current snapshot. Scenarios are explicit registry definitions containing
trigger, telemetry pattern, evidence, expected root cause, recommended future
action, risk, and recovery conditions.

Implemented scenarios are high CPU, error spike, database connection
exhaustion, queue backlog, memory leak, and failed deployment. A scenario tick
persists metrics and structured logs, creates a deployment record when
appropriate, and emits events to the Phase 4 ingestion service. Database
connection exhaustion emits DB utilization, latency, and error signals; the
existing correlation engine combines them into one incident.

Simulation execution metadata is persisted in `simulation_runs` by migration
`0004_simulation_runs`. No background thread, Redis, Celery task, real
infrastructure call, remediation, rollback, or automatic incident resolution
exists in this phase. Stopping a run stops generation and preserves historical
records.


PHASE 6 REDIS AND CELERY ASYNC INFRASTRUCTURE

The asynchronous event path is:

    Client -> FastAPI validation -> PostgreSQL event PERSISTED
        -> QUEUED -> Redis broker -> Celery worker
        -> EventProcessingService/IncidentEngine -> PostgreSQL

The API submits only an event_id and request/correlation ID. The worker loads
authoritative state from PostgreSQL, applies the existing event-to-alert-to-
incident service logic, and updates durable processing state. Direct service
execution remains available for synchronous tests and simulator use.

Event state is PERSISTED, QUEUED, PROCESSING, PROCESSED, or FAILED, with
attempts, processed_at, last error, request ID, and task ID persisted in
PostgreSQL. Duplicate tasks safely return for already processed events.
Celery uses JSON serialization, late acknowledgements, rejection on worker
loss, prefetch one, conservative configurable concurrency, and bounded retry
with jitter for transient failures. Domain validation failures do not retry.

Redis is infrastructure, not authoritative domain storage. If persistence
succeeds but broker submission fails, the API returns 503 and leaves the event
durably marked FAILED for later reprocessing. This phase deliberately does not
implement a transactional outbox; that is the future solution for the
database/broker commit window.

Worker health uses a real Celery inspect ping at `/health/worker`; liveness and
PostgreSQL/Redis readiness remain separate endpoints. The Docker worker uses
the same backend image and runs:

    celery -A app.workers.celery_app:celery_app worker --loglevel=INFO

## Phase 7 AI Investigation Layer

The Phase 7 boundary is intentionally one-way and read-only:

```text
Incident -> Context Builder -> Read-Only Tools -> One Bounded Agent
         -> Provider Abstraction -> Structured/Evidence Validation
         -> Deterministic Risk Validation -> ai_investigations
```

`IncidentContextBuilder` whitelists bounded incident, service, alert, event,
log, metric, deployment, and history fields. The tool registry accepts strict
input models for health, metrics, log search, deployments, incident history,
and events. It has no shell, arbitrary SQL, URL, write, or remediation
handler. Operational records are untrusted data and cannot redefine agent
behavior.

`AIInvestigationService` owns the business flow independently of Celery. It
claims `PENDING -> RUNNING` under a database lock, runs the provider outside a
database transaction, validates structured output and evidence identifiers,
applies minimum risk rules, and persists `COMPLETED` or safe `FAILED` metadata.
Celery only invokes the service and carries identifiers. Engineers/admins can
request investigations; authenticated users can read them. Recommendations
are never executed.

Phase 7 deliberately excludes RAG, embeddings, Qdrant retrieval, policy
enforcement, approvals, Tool Gateway, and autonomous remediation.

## Phase 8 RAG Knowledge Layer

Phase 8 makes Qdrant a derived index beside PostgreSQL:

```text
PostgreSQL Sources -> Parser/Cleaner -> Bounded Chunker
                   -> EmbeddingProvider -> Qdrant Collection
                   -> RAGService Retriever -> Phase 7 Context Builder -> AI
```

Runbooks and incidents remain sourced from their authoritative tables. The
small `knowledge_documents` table supplies active troubleshooting and
architecture documents. Cleaning redacts common credential-shaped values while
preserving operational terms and commands as untrusted text. Section-aware
deterministic chunks use configured size/overlap. Stable UUID5 point IDs and
source deletion before upsert make reindexing idempotent.

`MockEmbeddingProvider` is the default offline provider. Collection dimension
is checked against configuration, and metadata records document identity/type,
title, chunk, service/environment/version, timestamps, source, embedding model,
and dimension. `RAGService.retrieve` validates scores and payloads, bounds
results/context, returns citations, and uses controlled filter fallback.

The Phase 7 context builder calls read-only `search_knowledge`. Unavailable
Qdrant or embeddings produce explicit degraded RAG status and no fabricated
knowledge. Retrieved documents are reference material, not instructions;
current operational evidence remains authoritative. Celery owns indexing
orchestration, Qdrant HTTP operations are isolated in `QdrantRepository`, and
rebuild is explicit rather than automatic.

## Phase 9 Controlled Tool Gateway

Phase 9 introduces a narrow, simulator-only execution boundary. AI output and
API callers can request only explicitly registered tools:

```text
Recommendation/API
      -> Tool Gateway
      -> strict input schema
      -> role + incident environment checks
      -> registry risk decision
      -> PostgreSQL remediation action + audit event
      -> Celery low-risk execution
      -> simulator state + structured result + audit event
```

The registry is authoritative for tool name, description, input schema, risk,
roles, environments, mutation, and idempotency metadata. The five Phase 9
tools are `restart_service`, `scale_service`, `rollback_deployment`,
`clear_cache`, and `scale_workers`. Tool handlers are not exposed through
metadata and cannot be selected outside the registry. VIEWER users cannot
request or execute remediation; ENGINEER and ADMIN users can request the
registered tools.

All actions are simulated. There is no shell, arbitrary code, user-supplied
SQL or HTTP, Docker/Kubernetes/SSH/cloud call, Redis flush, or real service
operation. PostgreSQL stores the simulator state and the `0008_simulator_state`
migration adds the service state snapshot. The gateway enforces configured
replica/worker limits, validates idempotency keys, returns an existing action
for duplicate keys, and uses the existing remediation, approval, and audit
tables. Low-risk actions enter Celery and can complete; medium/high-risk
actions are persisted as `APPROVAL_REQUIRED`, so no implicit approval exists.
Critical or unknown tools are rejected. Execution has a bounded timeout,
structured public errors, retry handling at the task boundary, and no incident
resolution or incident lifecycle mutation.

## Phase 10 Policy and Human Approval

The Phase 10 execution path is:

```text
Request -> registry validation -> effective risk/environment
    -> PolicyEngine -> ALLOW | REQUIRE_APPROVAL | DENY
    -> pending approval when required -> policy/fingerprint re-check
    -> Tool Gateway -> simulator
```

`PolicyEngine` is the sole policy decision service. It uses exact or wildcard
action policies scoped by environment and effective risk, with explicit deny
precedence, deterministic specificity/version ordering, and default deny.
Critical actions remain universally denied. Tool definitions, not AI output,
determine effective risk and allowed environments.

Approvals are bound to a remediation action fingerprint containing the incident,
action type, normalized parameters, environment, effective risk, and policy
version. They expire using `APPROVAL_EXPIRATION_MINUTES`, cannot be reused for
another action, and high-risk requesters cannot approve their own actions.
Approval transitions lock the approval row; execution also locks the action and
re-evaluates policy, so changed policies, changed parameters, expired approval,
inactive requesters, and terminal incidents are blocked and audited.

Policy and approval events use the existing `audit_logs` table. The gateway is
still the only mutating execution boundary.

## Phase 11 Remediation Orchestration and Verification

`RemediationOrchestrator` is the application service used by the existing
Celery remediation task. It never calls simulator handlers directly: execution
continues through `ToolGateway`, which rechecks policy, approval, action
fingerprint, authorization, and idempotency. Idempotent retryable failures may
re-enter that same gateway a bounded number of times.

After execution, `VerificationEngine` reads fresh persisted simulator state
from the service snapshot. It evaluates typed, scenario-specific criteria and
stores a bounded verification history in `remediation_actions.result`. A
successful tool call alone cannot resolve an incident. Only the required
consecutive successful checks can transition `VERIFYING` to `RESOLVED`; failed
verification exhausts its bounded window and transitions through `FAILED` to
`ESCALATED`. Verification state is exposed by the remediation verification
endpoint.

## Finalization Notes

The repository is currently a local validation and demo environment. Compose
provides PostgreSQL, Redis, Qdrant, FastAPI, and a Celery worker; the React
console runs separately with Vite. Compose reads credentials and connection
URLs from `.env` rather than embedding them in the image or service definition.

The implementation has no frontend analytics, logs, metrics, deployments, or
audit-list API beyond the endpoints documented by the backend. The console
therefore shows only supported live data and explicit unavailable states. Full
production deployment, TLS termination, secret management, rate limiting,
refresh-token revocation, backups, and complete observability are not included.

