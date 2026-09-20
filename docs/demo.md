# OpsPilot Demo Flow

This demo uses the local simulator and preserves every policy, approval, and
verification gate. It is not a production deployment demonstration.

## Main flow: database connection exhaustion

1. Copy `.env.example` to `.env`, set local values, start Compose, migrate, and
   seed controlled development users.
2. Start the frontend and sign in as an engineer.
3. Open the dashboard and show the initial service posture.
4. Open Simulator and trigger `db_connection_exhaustion`.
5. Show the resulting telemetry, event, alert, and incident.
6. Request an investigation and wait for the persisted investigation result.
7. Show bounded evidence from metrics, logs, deployments, incident history, and
   retrieved knowledge where available.
8. Show the structured root-cause hypothesis and confidence as inference, not
   fact.
9. Show the high-risk remediation recommendation and PolicyEngine decision.
10. Approve only as an authorized, non-requesting engineer/admin when the
    approval is pending and unexpired.
11. Show ToolGateway execution in the simulator.
12. Show VerificationEngine checking fresh simulator state and recovery
    criteria.
13. Show the incident timeline and final `RESOLVED` state only after verification
    passes.

## Safety branch

Attempt a critical or unauthorized action, or submit an invalid tool parameter.
The expected result is a structured rejection, no simulator mutation, and an
audit entry. A blocked unsafe action is a successful safety outcome.

## Failure branch

Leave the simulator unhealthy after execution or inject a controlled tool/
verification failure in a dedicated validation environment. Show that execution
success does not equal recovery, the incident is not falsely resolved, and the
bounded failure path escalates when recovery cannot be established.

## Demo evidence to show

- dashboard metrics sourced from backend responses;
- incident event/alert correlation;
- AI facts, inference, and recommendation separated;
- policy decision and approval expiry;
- action fingerprint-bound approval;
- simulator state before/after execution;
- verification checks and thresholds;
- audit/timeline entries;
- blocked safety attempt.
