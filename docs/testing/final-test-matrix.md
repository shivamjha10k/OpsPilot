# Final Test Matrix

Status is based on commands actually executed in the current environment.
Implementation inspection alone is not a PASS.

| Area | Status | Evidence / blocker |
| --- | --- | --- |
| Authentication unit tests | BLOCKED | Current interpreter lacks declared backend runtime dependencies during full collection |
| RBAC unit tests | BLOCKED | Same backend collection blocker |
| API tests | BLOCKED | Requires backend dependencies and database setup |
| PostgreSQL integration | NOT RUN | Dedicated `TEST_DATABASE_URL` not configured |
| Incident state machine | BLOCKED | Full suite collection blocked |
| Event idempotency/correlation | NOT RUN | Requires dedicated PostgreSQL integration environment |
| Simulator unit tests | BLOCKED | Backend collection blocked |
| Redis | NOT RUN | Local Python Redis/Celery packages unavailable in prior probe |
| Celery | NOT RUN | Worker/service validation not executed in finalization |
| AI investigation | BLOCKED | Full suite collection blocked |
| RAG unit tests | BLOCKED | Full suite collection blocked |
| ToolGateway/Policy/Approval | BLOCKED | Full suite collection blocked |
| Remediation/Verification | BLOCKED | Full suite collection blocked |
| Phase 13 safety tests | BLOCKED | Collection blocked by missing `asyncpg` in active interpreter |
| Benchmark unit tests | PASS | `7 passed`; one pytest-asyncio configuration warning |
| Phase 14 harness syntax | PASS | `py_compile` and `compileall` passed |
| Frontend production build | PASS | `npm run build` passed |
| Frontend component tests | NOT RUN | No frontend test runner is configured |
| Docker Compose validation | NOT RUN | Docker command not executed in this environment |
| Alembic migration execution | NOT RUN | No dedicated database command executed |
| Secret scan | PASS (manual) | No obvious committed production secret detected; placeholders/default dev values were hardened |
| Dependency vulnerability scan | NOT RUN | `pip-audit`/equivalent not available or executed |
| Phase 14 local read-only probe | PASS (limited) | API/Qdrant available; Redis/Celery Python clients unavailable |
| Phase 15 benchmark results | NOT RUN | Framework/catalog validated; no real baseline/OpsPilot trials supplied |
