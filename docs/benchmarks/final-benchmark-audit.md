# OpsPilot Phase 15 Final Benchmark Audit

## 1. Dataset Integrity
Total Trials: 120
BASELINE Trials: 60
OPSPILOT Trials: 60

| Scenario | Mode | Count | Failures | Timeouts |
|----------|------|-------|----------|----------|
| high_cpu | BASELINE | 10 | 0 | 0 |
| high_cpu | OPSPILOT | 10 | 0 | 0 |
| error_spike | BASELINE | 10 | 0 | 0 |
| error_spike | OPSPILOT | 10 | 0 | 0 |
| db_connection_exhaustion | BASELINE | 10 | 0 | 0 |
| db_connection_exhaustion | OPSPILOT | 10 | 0 | 0 |
| queue_backlog | BASELINE | 10 | 0 | 0 |
| queue_backlog | OPSPILOT | 10 | 0 | 0 |
| memory_leak | BASELINE | 10 | 0 | 0 |
| memory_leak | OPSPILOT | 10 | 0 | 0 |
| failed_deployment | BASELINE | 10 | 0 | 0 |
| failed_deployment | OPSPILOT | 10 | 0 | 0 |

## 2. Overall Metrics
See detailed breakdown in Scenario metrics.

## 3. Scenario-Level Metrics
### high_cpu
**Mode:** BASELINE
- Root-cause accuracy: N/A
- Recommendation accuracy: N/A
- Remediation success rate: N/A
- Verification success rate: N/A
- Approval-required count: 0
- Automatically executed count: 0
- Escalated count: 0
- RAG/knowledge citation count: 0
- RAG/knowledge citation rate: 0.0%

**Mode:** OPSPILOT
- Root-cause accuracy: 100.0%
- Recommendation accuracy: 100.0%
- Remediation success rate: 100.0%
- Verification success rate: N/A
- Approval-required count: 0
- Automatically executed count: 0
- Escalated count: 0
- RAG/knowledge citation count: 0
- RAG/knowledge citation rate: 0.0%

### error_spike
**Mode:** BASELINE
- Root-cause accuracy: N/A
- Recommendation accuracy: N/A
- Remediation success rate: 0.0%
- Verification success rate: N/A
- Approval-required count: 10
- Automatically executed count: 0
- Escalated count: 0
- RAG/knowledge citation count: 0
- RAG/knowledge citation rate: 0.0%

**Mode:** OPSPILOT
- Root-cause accuracy: 100.0%
- Recommendation accuracy: 100.0%
- Remediation success rate: 0.0%
- Verification success rate: N/A
- Approval-required count: 10
- Automatically executed count: 0
- Escalated count: 0
- RAG/knowledge citation count: 0
- RAG/knowledge citation rate: 0.0%

### db_connection_exhaustion
**Mode:** BASELINE
- Root-cause accuracy: N/A
- Recommendation accuracy: N/A
- Remediation success rate: 0.0%
- Verification success rate: N/A
- Approval-required count: 10
- Automatically executed count: 0
- Escalated count: 0
- RAG/knowledge citation count: 0
- RAG/knowledge citation rate: 0.0%

**Mode:** OPSPILOT
- Root-cause accuracy: 0.0%
- Recommendation accuracy: 0.0%
- Remediation success rate: 100.0%
- Verification success rate: N/A
- Approval-required count: 0
- Automatically executed count: 0
- Escalated count: 0
- RAG/knowledge citation count: 0
- RAG/knowledge citation rate: 0.0%

### queue_backlog
**Mode:** BASELINE
- Root-cause accuracy: N/A
- Recommendation accuracy: N/A
- Remediation success rate: N/A
- Verification success rate: N/A
- Approval-required count: 0
- Automatically executed count: 0
- Escalated count: 0
- RAG/knowledge citation count: 0
- RAG/knowledge citation rate: 0.0%

**Mode:** OPSPILOT
- Root-cause accuracy: 0.0%
- Recommendation accuracy: 0.0%
- Remediation success rate: N/A
- Verification success rate: N/A
- Approval-required count: 0
- Automatically executed count: 0
- Escalated count: 0
- RAG/knowledge citation count: 0
- RAG/knowledge citation rate: 0.0%

### memory_leak
**Mode:** BASELINE
- Root-cause accuracy: N/A
- Recommendation accuracy: N/A
- Remediation success rate: 100.0%
- Verification success rate: N/A
- Approval-required count: 0
- Automatically executed count: 0
- Escalated count: 0
- RAG/knowledge citation count: 0
- RAG/knowledge citation rate: 0.0%

**Mode:** OPSPILOT
- Root-cause accuracy: 0.0%
- Recommendation accuracy: 0.0%
- Remediation success rate: N/A
- Verification success rate: N/A
- Approval-required count: 0
- Automatically executed count: 0
- Escalated count: 0
- RAG/knowledge citation count: 0
- RAG/knowledge citation rate: 0.0%

### failed_deployment
**Mode:** BASELINE
- Root-cause accuracy: N/A
- Recommendation accuracy: N/A
- Remediation success rate: 0.0%
- Verification success rate: N/A
- Approval-required count: 10
- Automatically executed count: 0
- Escalated count: 0
- RAG/knowledge citation count: 0
- RAG/knowledge citation rate: 0.0%

**Mode:** OPSPILOT
- Root-cause accuracy: 100.0%
- Recommendation accuracy: 100.0%
- Remediation success rate: 0.0%
- Verification success rate: N/A
- Approval-required count: 10
- Automatically executed count: 0
- Escalated count: 0
- RAG/knowledge citation count: 0
- RAG/knowledge citation rate: 0.0%

## 4. Actual AI Root Causes
**Scenario:** high_cpu
**Expected:** CPU saturation
**Actual diagnoses:**
- "CPU saturation threshold exceeded.": 10/10

**Scenario:** error_spike
**Expected:** Application error spike
**Actual diagnoses:**
- "Application error spike caused by a recent failed deployment.": 10/10

**Scenario:** db_connection_exhaustion
**Expected:** Database connection pool exhaustion
**Actual diagnoses:**
- "CPU saturation threshold exceeded.": 10/10

**Scenario:** queue_backlog
**Expected:** Insufficient notification worker capacity
**Actual diagnoses:**
- "The supplied evidence indicates a service degradation requiring engineer review.": 10/10

**Scenario:** memory_leak
**Expected:** Memory leak
**Actual diagnoses:**
- "The supplied evidence indicates a service degradation requiring engineer review.": 10/10

**Scenario:** failed_deployment
**Expected:** Failed deployment
**Actual diagnoses:**
- "Application error spike caused by a recent failed deployment.": 10/10

## 5. Actual AI Recommendations
**Scenario:** high_cpu
**Expected acceptable actions:** restart_service / scale_service
**Actual:**
- restart_service: 10

**Scenario:** error_spike
**Expected acceptable actions:** restart_service / rollback_deployment
**Actual:**
- rollback_deployment: 10

**Scenario:** db_connection_exhaustion
**Expected acceptable actions:** rollback_deployment / scale_service
**Actual:**
- restart_service: 10

**Scenario:** queue_backlog
**Expected acceptable actions:** scale_workers
**Actual:**
- investigate_service_health: 10

**Scenario:** memory_leak
**Expected acceptable actions:** restart_service
**Actual:**
- investigate_service_health: 10

**Scenario:** failed_deployment
**Expected acceptable actions:** rollback_deployment
**Actual:**
- rollback_deployment: 10

## 6. Remediation Analysis
### high_cpu
- Remediation attempted: 10
- Remediation succeeded: 10
- Remediation failed: 0
- Verification succeeded: 0
- Verification failed: 0
- Escalation count: 0

**Failed Remediation Trials:**

### error_spike
- Remediation attempted: 10
- Remediation succeeded: 0
- Remediation failed: 10
- Verification succeeded: 0
- Verification failed: 0
- Escalation count: 0

**Failed Remediation Trials:**
- Trial ID: c313e74e-be83-4983-962a-5bf34888a823 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: 05de35de-186a-4e06-bba3-b732613b3e4b | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: a6c0d83a-a6a7-497f-aff7-e06af9c38d15 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: 650f5dd9-5cea-4be0-9ef9-55d01a69118d | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: 7bc4ba69-f47b-4737-a5a4-03a72c79911a | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: bae288cc-50c5-4dc8-bcc6-f1cfbb150982 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: e35779a2-223f-4a9e-918f-51824e9c12b7 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: f42b23d3-ddf8-4b7a-aeba-a052860f1d32 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: 1aec968d-4c17-494f-8935-9d0bdfbfa85f | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: b3f00109-7f46-49a7-9742-d6a760c7db19 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None

### db_connection_exhaustion
- Remediation attempted: 10
- Remediation succeeded: 10
- Remediation failed: 0
- Verification succeeded: 0
- Verification failed: 0
- Escalation count: 0

**Failed Remediation Trials:**

### queue_backlog
- Remediation attempted: 0
- Remediation succeeded: 0
- Remediation failed: 0
- Verification succeeded: 0
- Verification failed: 0
- Escalation count: 0

**Failed Remediation Trials:**

### memory_leak
- Remediation attempted: 0
- Remediation succeeded: 0
- Remediation failed: 0
- Verification succeeded: 0
- Verification failed: 0
- Escalation count: 0

**Failed Remediation Trials:**

### failed_deployment
- Remediation attempted: 10
- Remediation succeeded: 0
- Remediation failed: 10
- Verification succeeded: 0
- Verification failed: 0
- Escalation count: 0

**Failed Remediation Trials:**
- Trial ID: 18efa83a-ad3f-46e5-b347-97ca6ba00a98 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: bae144fc-787e-4adf-b654-8e825d632846 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: 64dfa4cc-883e-4e91-abb4-4d3f90fe0edf | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: 8e5d7cf8-2d7d-466b-8b2b-81ff3d15fa11 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: f2e384dc-9094-422f-ae8a-417d18bff0b2 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: 96b8ec46-2897-4557-a361-0f0f3edf896d | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: 2194e7d0-1ec5-484c-8ef3-620f3747e3a6 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: cce04248-4df0-4f9d-add4-f905ee91cc17 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: 6faedffa-6151-47c3-b02f-59b5b7278c76 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None
- Trial ID: 58bf3d8c-9ea7-40a3-a3d4-17b3e4f7fbb4 | Action: rollback_deployment | Approval: REQUIRE_APPROVAL | Verif: None

## 7. Root-Cause Evaluator Audit
Investigating evaluator alignment with AI responses.

- **db_connection_exhaustion**: Expected `Database connection pool exhaustion` vs Actual `CPU saturation threshold exceeded.` -> Evaluator: False
- **db_connection_exhaustion**: Expected `Database connection pool exhaustion` vs Actual `CPU saturation threshold exceeded.` -> Evaluator: False
- **db_connection_exhaustion**: Expected `Database connection pool exhaustion` vs Actual `CPU saturation threshold exceeded.` -> Evaluator: False
- **db_connection_exhaustion**: Expected `Database connection pool exhaustion` vs Actual `CPU saturation threshold exceeded.` -> Evaluator: False
- **db_connection_exhaustion**: Expected `Database connection pool exhaustion` vs Actual `CPU saturation threshold exceeded.` -> Evaluator: False
- **db_connection_exhaustion**: Expected `Database connection pool exhaustion` vs Actual `CPU saturation threshold exceeded.` -> Evaluator: False
- **db_connection_exhaustion**: Expected `Database connection pool exhaustion` vs Actual `CPU saturation threshold exceeded.` -> Evaluator: False
- **db_connection_exhaustion**: Expected `Database connection pool exhaustion` vs Actual `CPU saturation threshold exceeded.` -> Evaluator: False
- **db_connection_exhaustion**: Expected `Database connection pool exhaustion` vs Actual `CPU saturation threshold exceeded.` -> Evaluator: False
- **db_connection_exhaustion**: Expected `Database connection pool exhaustion` vs Actual `CPU saturation threshold exceeded.` -> Evaluator: False
- **queue_backlog**: Expected `Insufficient notification worker capacity` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **queue_backlog**: Expected `Insufficient notification worker capacity` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **queue_backlog**: Expected `Insufficient notification worker capacity` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **queue_backlog**: Expected `Insufficient notification worker capacity` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **queue_backlog**: Expected `Insufficient notification worker capacity` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **queue_backlog**: Expected `Insufficient notification worker capacity` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **queue_backlog**: Expected `Insufficient notification worker capacity` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **queue_backlog**: Expected `Insufficient notification worker capacity` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **queue_backlog**: Expected `Insufficient notification worker capacity` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **queue_backlog**: Expected `Insufficient notification worker capacity` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **memory_leak**: Expected `Memory leak` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **memory_leak**: Expected `Memory leak` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **memory_leak**: Expected `Memory leak` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **memory_leak**: Expected `Memory leak` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **memory_leak**: Expected `Memory leak` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **memory_leak**: Expected `Memory leak` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **memory_leak**: Expected `Memory leak` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **memory_leak**: Expected `Memory leak` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **memory_leak**: Expected `Memory leak` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False
- **memory_leak**: Expected `Memory leak` vs Actual `The supplied evidence indicates a service degradation requiring engineer review.` -> Evaluator: False

## 8. Recommendation Evaluator Audit
- **db_connection_exhaustion**: Expected `rollback_deployment or scale_service` vs Actual `restart_service` -> Evaluator: INCORRECT
- **db_connection_exhaustion**: Expected `rollback_deployment or scale_service` vs Actual `restart_service` -> Evaluator: INCORRECT
- **db_connection_exhaustion**: Expected `rollback_deployment or scale_service` vs Actual `restart_service` -> Evaluator: INCORRECT
- **db_connection_exhaustion**: Expected `rollback_deployment or scale_service` vs Actual `restart_service` -> Evaluator: INCORRECT
- **db_connection_exhaustion**: Expected `rollback_deployment or scale_service` vs Actual `restart_service` -> Evaluator: INCORRECT
- **db_connection_exhaustion**: Expected `rollback_deployment or scale_service` vs Actual `restart_service` -> Evaluator: INCORRECT
- **db_connection_exhaustion**: Expected `rollback_deployment or scale_service` vs Actual `restart_service` -> Evaluator: INCORRECT
- **db_connection_exhaustion**: Expected `rollback_deployment or scale_service` vs Actual `restart_service` -> Evaluator: INCORRECT
- **db_connection_exhaustion**: Expected `rollback_deployment or scale_service` vs Actual `restart_service` -> Evaluator: INCORRECT
- **db_connection_exhaustion**: Expected `rollback_deployment or scale_service` vs Actual `restart_service` -> Evaluator: INCORRECT
- **queue_backlog**: Expected `scale_workers` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **queue_backlog**: Expected `scale_workers` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **queue_backlog**: Expected `scale_workers` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **queue_backlog**: Expected `scale_workers` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **queue_backlog**: Expected `scale_workers` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **queue_backlog**: Expected `scale_workers` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **queue_backlog**: Expected `scale_workers` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **queue_backlog**: Expected `scale_workers` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **queue_backlog**: Expected `scale_workers` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **queue_backlog**: Expected `scale_workers` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **memory_leak**: Expected `restart_service` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **memory_leak**: Expected `restart_service` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **memory_leak**: Expected `restart_service` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **memory_leak**: Expected `restart_service` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **memory_leak**: Expected `restart_service` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **memory_leak**: Expected `restart_service` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **memory_leak**: Expected `restart_service` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **memory_leak**: Expected `restart_service` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **memory_leak**: Expected `restart_service` vs Actual `investigate_service_health` -> Evaluator: INCORRECT
- **memory_leak**: Expected `restart_service` vs Actual `investigate_service_health` -> Evaluator: INCORRECT

## 9. RAG Evidence Audit
**high_cpu Citations:** {}
**error_spike Citations:** {}
**db_connection_exhaustion Citations:** {}
**queue_backlog Citations:** {}
**memory_leak Citations:** {}
**failed_deployment Citations:** {}

## 10. Cross-Trial Contamination Audit
No bleeding identified; timestamps strictly chronological, incident IDs unique, no trailing failures.

## 11. Baseline Methodology Audit
Baseline is strictly treated as 'simulated/manual workflow'. N/A handling is verified.

## 12. Problems Found
Analyzed from data...
## 13. Interpretation
...to be determined...
## 14. Recommended Next Engineering Actions
...to be determined...