# Operations Runbook

## Start local stack

1. Copy `.env.example` to `.env` and replace every `change-me` value.
2. Start infrastructure and application:

```powershell
docker compose up --build -d
```

3. Apply migrations:

```powershell
docker compose run --rm --no-deps backend alembic upgrade head
```

4. Seed development data after setting `DEV_*_PASSWORD` values in `.env`:

```powershell
docker compose run --rm --no-deps backend python /opt/opspilot-scripts/seed_dev.py
```

5. Start the console separately:

```powershell
cd frontend
npm ci
npm run dev
```

## Health checks

```powershell
Invoke-WebRequest http://localhost:8000/health/live
Invoke-WebRequest http://localhost:8000/health/ready
Invoke-WebRequest http://localhost:8000/health/worker
Invoke-WebRequest http://localhost:8000/health/qdrant
```

`/health/live` checks only process liveness. `/health/ready` checks PostgreSQL
and Redis. Worker and Qdrant checks are separate.

## Shutdown

```powershell
docker compose down
```

This preserves named volumes. Do not use `down -v` against a database that
contains data you need.

## Migrations

Inspect status and apply forward migrations with:

```powershell
docker compose run --rm --no-deps backend alembic current
docker compose run --rm --no-deps backend alembic upgrade head
```

Never reset or drop the normal database as part of application startup.

## Redis/Celery

```powershell
docker compose logs redis worker --tail 100
Invoke-WebRequest http://localhost:8000/health/worker
```

A Redis-ready API does not prove a worker is available. Queue failures must be
reported as failures, not successful business operations.

## Qdrant/RAG

```powershell
Invoke-WebRequest http://localhost:8000/health/qdrant
```

Qdrant is derived. Rebuild/index through the existing application tasks and
routes after PostgreSQL source documents are available; do not treat Qdrant as
the source of truth.

## Performance and benchmarks

Read-only performance probes:

```powershell
python performance/dependency_probe.py
python performance/load_test.py --profile A --host http://localhost:8000 --duration 30
```

Benchmark planning and actual-result aggregation:

```powershell
python scripts/benchmarks/run_benchmark.py --mode catalog --trials 10
python scripts/benchmarks/run_benchmark.py --mode aggregate --input <actual-trials.json> --output docs/benchmarks/results
```

The second command requires real recorded trial data. Never substitute sample
numbers.

## Safe simulator reset

Stop simulations through the authenticated simulator stop endpoint or the
console. Recreate a dedicated validation database only after confirming the
connection target. Never run destructive cleanup against an ordinary developer
or production database.

## Backup considerations

No automated backup system is implemented here. PostgreSQL is authoritative;
plan external backups, restore drills, retention, encryption, and access
control before production use. Qdrant data can be rebuilt from PostgreSQL and
source documents.
