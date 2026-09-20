# OpsPilot Testing Strategy

Phase 13 validates failure behavior and security boundaries. It does not add load testing or benchmark infrastructure; those belong to later phases.

## Test pyramid

- **Unit**: deterministic policy, state-machine, simulator, AI boundary, RAG, gateway, and verification tests.
- **Integration**: PostgreSQL-backed repository, incident, simulator, and API tests. These require `TEST_DATABASE_URL` and never target the normal development database.
- **Security**: authentication, RBAC, default-deny, approval binding, prompt-injection-as-data, no-fake-resolution, and gateway-boundary tests.
- **E2E**: complete incident-to-remediation-to-verification flows when PostgreSQL, Redis, Celery, and Qdrant are available.

## Commands

From `backend/` with the declared development dependencies installed:

```bash
pytest -m unit
pytest -m security
pytest -m integration
pytest
pytest --cov=app --cov-report=term-missing
```

Integration tests are skipped unless `TEST_DATABASE_URL` is set. Use a dedicated database or schema, for example:

```text
TEST_DATABASE_URL=postgresql+asyncpg://.../opspilot_test
```

Never point `TEST_DATABASE_URL` at the normal developer database. Migrations should be applied to the test database before integration runs.

Frontend validation is currently build-level because the frontend did not previously contain a test runner:

```bash
cd frontend
npm run build
```

## Failure injection

Use dependency injection or test doubles for Redis, Celery, Qdrant, AI providers, ToolGateway handlers, and verification reads. Do not require every service to be online for unit tests. Failure tests must assert persisted state, audit behavior, bounded retries, and the absence of false resolution.

## Safety invariants

The highest-value regressions are:

- a client cannot transition an incident directly to `RESOLVED`;
- execution success cannot resolve an incident without fresh verification;
- failed verification cannot resolve an incident;
- AI tools are read-only and cannot invoke mutating gateway tools;
- registry risk, policy, and approval checks remain server-side;
- prompt-injected logs/runbooks remain data;
- critical or unknown actions are denied;
- retries re-enter the ToolGateway and remain bounded.

Coverage percentages are reported only from an actually executed coverage command. No coverage number is inferred from test count.
