# OpsPilot Security

## Security posture

Current classification: **READY FOR LOCAL E2E VALIDATION; NOT PRODUCTION READY**.
OpsPilot is a simulator-first modular monolith. Backend authorization and policy
checks are authoritative; the frontend is only a usability layer.

## Threat model

The primary threats are unauthorized API access, forged approvals, action
parameter tampering, stale policy decisions, prompt injection through
operational data, accidental real-infrastructure execution, leaked secrets, and
false incident resolution.

## Identity and RBAC

Authentication uses Argon2 password hashing and short-lived JWT access tokens
with separate refresh tokens. The server loads the user and role from
PostgreSQL; client-supplied roles and user IDs are not trusted. Roles are
`ADMIN`, `ENGINEER`, and `VIEWER`. Protected routes require authentication and
role dependencies. Inactive users are rejected.

Refresh tokens are stateless in the current implementation. Logout asks the
client to discard tokens; server-side refresh revocation and rotation are not
implemented. Login rate limiting is not implemented.

## Secrets

Secrets and credentials must be provided through environment variables. `.env`
and other `.env.*` files are ignored; `.env.example` contains placeholders only.
Compose requires database and JWT settings from the environment. Do not commit
API keys, bearer tokens, passwords, private keys, or database connection strings
with usable credentials.

## AI and prompt injection

AI output is untrusted and cannot directly execute privileged actions. AI tools
are read-only and bounded. Logs, runbooks, incidents, and retrieved documents
are treated as data, not instructions. RAG cleaning redacts common credential-
shaped values, and retrieved references cannot call tools.

The actual mutation boundary is:

```text
AI output -> structured validation -> server risk -> RBAC -> PolicyEngine
           -> approval when required -> ToolGateway -> simulator -> verification
```

The system does not expose shell, arbitrary SQL, arbitrary HTTP, SSH, Docker,
Kubernetes, or cloud execution through AI or the API.

## Policy and approval security

PolicyEngine defaults to deny for unknown actions, unknown environments, missing
policies, inactive callers, and critical risk. ToolRegistry metadata determines
effective risk; AI cannot lower it. Policy is re-evaluated at execution.

Approvals are server-side records bound to the exact remediation action through
an action fingerprint containing the incident, action, parameters, environment,
risk, and policy snapshot. Approvals expire, high-risk requesters cannot approve
their own actions, and changed actions or policies invalidate stale approval.

## Remediation and resolution

Tool execution success is not incident recovery. VerificationEngine reads fresh
persisted simulator state and requires scenario-specific criteria and bounded
consecutive checks before resolution. Failed verification escalates. Incident
status cannot be set to `RESOLVED` directly by a client API.

## Data and database safety

PostgreSQL is the source of truth. SQLAlchemy bound queries and Pydantic input
models are used; user-supplied SQL is not accepted. Qdrant is a rebuildable
derived index. Foreign keys, unique idempotency keys, typed enums, and audit
records protect domain integrity.

## Audit and logging

Policy evaluation, approval, remediation, verification, escalation, and
resolution events are written to `audit_logs`. Logs must not contain passwords,
JWTs, refresh tokens, API keys, authorization headers, or credentials. Request
IDs are returned in structured application errors when available.

## Environment isolation

The simulator is the only execution environment. Production environment values
remain subject to server-side policy and critical-risk blocking. Local Compose
is intended for development and validation, not production deployment.

## Known limitations

- No distributed rate limiter or login brute-force protection.
- Refresh token revocation/rotation is not implemented.
- No production secret manager, TLS edge, backup automation, or container scan
  is configured in this repository.
- The active local interpreter has previously lacked declared backend packages;
  full backend validation requires the declared environment and dedicated
  PostgreSQL/Redis/Celery/Qdrant services.
