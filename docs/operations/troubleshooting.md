# Troubleshooting

## Backend does not start

Check configuration and logs:

```powershell
docker compose config
docker compose logs backend --tail 100
```

Confirm `.env` exists and required Compose variables are set. Do not put secrets
in `docker-compose.yml`.

## PostgreSQL unavailable

Check:

```powershell
docker compose ps postgres
docker compose logs postgres --tail 100
```

Wait for the health check, then verify `/health/ready`. Confirm `DATABASE_URL`
uses the Compose hostname `postgres` inside containers.

## Redis unavailable

Check `docker compose ps redis` and `docker compose logs redis`. The API may
remain live while readiness and asynchronous queue operations fail. Do not
interpret liveness as queue health.

## Celery worker unavailable

Check:

```powershell
docker compose logs worker --tail 100
Invoke-WebRequest http://localhost:8000/health/worker
```

A healthy Redis broker does not mean a worker is consuming tasks.

## Qdrant unavailable

Use `/health/qdrant` and inspect Qdrant logs. Investigation can operate in a
degraded RAG mode according to the existing service behavior. PostgreSQL source
documents remain authoritative.

## Frontend cannot reach API

Confirm the API is on port 8000 and `frontend/.env` contains:

```text
VITE_API_BASE_URL=http://localhost:8000
```

Check browser network errors and CORS origins in `.env`.

## Migration failure

Inspect the current revision before applying changes:

```powershell
docker compose run --rm --no-deps backend alembic current
docker compose run --rm --no-deps backend alembic history
```

Do not drop tables or downgrade production data to repair an unknown failure.

## Authentication failure

Confirm the user is active, the JWT secret is consistent across API/worker
configuration, and development seed passwords were explicitly set. Do not
paste tokens into logs or issue reports.

## AI provider failure

Local development should use `AI_PROVIDER=mock`. Check investigation status,
worker logs, timeout settings, and retry limits. A failed investigation must not
create an executable remediation.

## RAG indexing failure

Check Qdrant readiness, embedding dimension/model configuration, and source
record status. Retry indexing from PostgreSQL source data; do not manually edit
vector points as a source-of-truth fix.

## Tool execution failure

Inspect the remediation action, policy decision, approval state, action
fingerprint, and audit entries. Do not retry by bypassing ToolGateway or policy.

## Approval failure

Verify the approval is pending, unexpired, bound to the action, and the actor
has an authorized role. A requester cannot self-approve high-risk work.

## Verification failure

Execution success is not recovery. Inspect fresh simulator state and recorded
criteria. Failed verification should remain unresolved and follow bounded retry
and escalation behavior.

## Simulator failure

Confirm `SIMULATOR_ENABLED=true` only in the intended development environment,
that the target service exists, and that the scenario is not already running.
