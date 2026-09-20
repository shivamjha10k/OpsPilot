import argparse
import asyncio
import json
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import httpx

from app.benchmarks.adapter import BenchmarkAdapter, execute_trials
from app.benchmarks.models import BenchmarkConfig, TrialResult, TrialStatus, ScenarioGroundTruth
from app.core.database import SessionLocal
from app.rag.service import RAGService

class OpsPilotLiveAdapter(BenchmarkAdapter):
    def __init__(self, ground_truths: dict[str, ScenarioGroundTruth]):
        self.ground_truths = ground_truths
        self.base_url = "http://localhost:8000/api/v1"
        self.db_url = "postgresql://opspilot:change-me-local-only@localhost:5433/opspilot"

    def run_trial(self, *, scenario: str, seed: int, trial_number: int, mode: str) -> TrialResult:
        return asyncio.run(self._run_trial_async(scenario, seed, trial_number, mode))

    async def _run_trial_async(self, scenario: str, seed: int, trial_number: int, mode: str) -> TrialResult:
        print(f"\n--- Starting Trial {trial_number} ({mode}): {scenario} [Seed: {seed}] ---")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Login
            resp = await client.post(f"{self.base_url}/auth/login", json={"email": "admin@opspilot.local", "password": "change-me-admin"})
            resp.raise_for_status()
            token = resp.json()["data"]["access_token"]
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            
            # 2. Stop running simulations
            sims_resp = await client.get(f"{self.base_url}/simulator/simulations", headers=headers)
            sims_resp.raise_for_status()
            for sim in sims_resp.json()["data"]:
                if sim["status"] == "RUNNING":
                    await client.post(f"{self.base_url}/simulator/simulations/{sim['id']}/stop", json={}, headers=headers)
            await asyncio.sleep(2)
            
            # 3. Trigger simulation
            trigger_payload = {"configuration": {"random_seed": seed, "tick_interval_seconds": 1.0}}
            trig_resp = await client.post(f"{self.base_url}/simulator/scenarios/{scenario}/trigger", json=trigger_payload, headers=headers)
            if trig_resp.status_code not in (200, 201, 202):
                raise RuntimeError(f"Failed to trigger scenario: {trig_resp.text}")
            
            sim_data = trig_resp.json()["data"]
            trigger_at = datetime.fromisoformat(sim_data["started_at"].replace("Z", "+00:00"))
            target_service_id = sim_data["target_service_id"]
            
            # Connect to DB
            conn = await asyncpg.connect(self.db_url)
            try:
                # 4. Wait for incident
                incident_id = None
                detected_at = None
                for attempt in range(120):
                    inc = await conn.fetchrow("""
                        SELECT id, detected_at, status, resolved_at FROM incidents 
                        WHERE service_id = $1 AND status NOT IN ('RESOLVED', 'FAILED', 'ESCALATED')
                        ORDER BY created_at DESC LIMIT 1
                    """, uuid.UUID(target_service_id))
                    if inc:
                        incident_id = str(inc["id"])
                        detected_at = inc["detected_at"]
                        break
                    else:
                        if attempt % 10 == 0:
                            print(f"[{mode}] Polling for incident on service {target_service_id} (attempt {attempt + 1}/120)...")
                    await asyncio.sleep(1)
                
                if not incident_id:
                    print(f"[{mode}] Timeout reached! Target Service ID was: {target_service_id}")
                    raise RuntimeError("Incident not created within timeout")
                
                print(f"[{mode}] Incident {incident_id} detected.")

                if mode.startswith("BASELINE"):
                    # Simulated manual workflow: directly post remediation
                    expected_action = self.ground_truths[scenario].expected_action
                    print(f"[{mode}] Emulating manual action: {expected_action}")
                    
                    params = {"service_id": target_service_id}
                    if expected_action == "scale_workers":
                        params["desired_workers"] = 10
                    elif expected_action == "scale_service":
                        params["desired_replicas"] = 5
                    elif expected_action == "rollback_deployment":
                        dep = await conn.fetchrow("SELECT id FROM deployments WHERE service_id = $1 ORDER BY deployed_at DESC LIMIT 1", uuid.UUID(target_service_id))
                        params["deployment_id"] = str(dep["id"]) if dep else str(uuid.uuid4())
                        
                    await client.post(f"{self.base_url}/incidents/{incident_id}/remediation", json={
                        "action_type": expected_action,
                        "parameters": params,
                        "idempotency_key": str(uuid.uuid4())
                    }, headers=headers)
                    diagnosed_at = None
                    root_cause = None
                    recommendation = None
                    risk_level = None
                    retrieved_docs = []
                else:
                    # OPSPILOT Mode: wait for AI Investigation
                    print(f"[{mode}] Waiting for AI Investigation...")
                    diagnosed_at = None
                    root_cause = None
                    recommendation = None
                    risk_level = None
                    retrieved_docs = []
                    for _ in range(60):
                        inv = await conn.fetchrow("""
                            SELECT status, completed_at, root_cause, recommendation_data, risk_level, knowledge_references
                            FROM ai_investigations
                            WHERE incident_id = $1
                            ORDER BY created_at DESC LIMIT 1
                        """, uuid.UUID(incident_id))
                        if inv and inv["status"] in ("COMPLETED", "FAILED"):
                            if inv["status"] == "COMPLETED":
                                diagnosed_at = inv["completed_at"]
                                root_cause = inv["root_cause"]
                                rec_data = json.loads(inv["recommendation_data"]) if inv["recommendation_data"] else {}
                                recommendation = rec_data.get("type")
                                risk_level = inv["risk_level"]
                                retrieved_docs = json.loads(inv["knowledge_references"]) if inv["knowledge_references"] else []
                            break
                        await asyncio.sleep(1)

                # Wait for Remediation Action
                print(f"[{mode}] Waiting for remediation...")
                remed_requested = None
                exec_started = None
                exec_completed = None
                policy_decision = None
                exec_success = None
                verif_success = None
                
                for _ in range(15):
                    rem = await conn.fetchrow("""
                        SELECT status, requested_at, executed_at, completed_at, policy_decision, result
                        FROM remediation_actions
                        WHERE incident_id = $1
                        ORDER BY requested_at DESC LIMIT 1
                    """, uuid.UUID(incident_id))
                    if rem and rem["status"] in ("COMPLETED", "FAILED", "APPROVAL_REQUIRED"):
                        remed_requested = rem["requested_at"]
                        exec_started = rem["executed_at"]
                        exec_completed = rem["completed_at"]
                        policy_decision = rem["policy_decision"]
                        exec_success = (rem["status"] == "COMPLETED")
                        
                        res = json.loads(rem["result"]) if rem["result"] else {}
                        verif_status = res.get("verification_status")
                        if verif_status == "PASSED":
                            verif_success = True
                        elif verif_status == "FAILED":
                            verif_success = False
                        break
                    await asyncio.sleep(1)

                # Wait for Incident to Resolve/Fail
                print(f"[{mode}] Waiting for incident resolution...")
                resolved_at = None
                for _ in range(30):
                    inc = await conn.fetchrow("SELECT status, resolved_at FROM incidents WHERE id = $1", uuid.UUID(incident_id))
                    if inc["status"] in ("RESOLVED", "ESCALATED", "FAILED"):
                        resolved_at = inc["resolved_at"] if inc["status"] == "RESOLVED" else None
                        break
                    await asyncio.sleep(1)

                timestamps = {
                    "trigger_at": trigger_at,
                    "detected_at": detected_at,
                    "diagnosed_at": diagnosed_at,
                    "remediation_requested_at": remed_requested,
                    "execution_started_at": exec_started,
                    "execution_completed_at": exec_completed,
                    "resolved_at": resolved_at
                }

                return TrialResult(
                    scenario=scenario,
                    seed=seed,
                    mode=mode,
                    status=TrialStatus.VALID,
                    timestamps=timestamps,
                    root_cause=root_cause,
                    recommendation_action=recommendation,
                    risk_level=risk_level,
                    rag_retrieved_documents=retrieved_docs,
                    approval_outcome=policy_decision,
                    execution_success=exec_success,
                    verification_success=verif_success
                )

            except Exception as e:
                import traceback
                traceback.print_exc()
                return TrialResult(
                    scenario=scenario,
                    seed=seed,
                    mode=mode,
                    status=TrialStatus.FAILED,
                    failure_reason=str(e)
                )
            finally:
                if 'incident_id' in locals() and incident_id:
                    # Update status to ESCALATED so it is no longer active for subsequent trials
                    await conn.execute("UPDATE incidents SET status = 'ESCALATED' WHERE id = $1 AND status NOT IN ('RESOLVED', 'FAILED', 'ESCALATED')", uuid.UUID(incident_id))
                await conn.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_file", type=Path)
    parser.add_argument("output_file", type=Path)
    args = parser.parse_args()

    with open(args.plan_file, "r", encoding="utf-8-sig") as f:
        plan = json.load(f)

    config = BenchmarkConfig(**plan["configuration"])
    
    ground_truths = {
        sgt["scenario"]: ScenarioGroundTruth(
            scenario=sgt["scenario"],
            trigger_condition=sgt["trigger_condition"],
            expected_root_cause=sgt["expected_root_cause"],
            acceptable_root_causes=frozenset(sgt["acceptable_root_causes"]),
            expected_evidence=tuple(sgt["expected_evidence"]),
            expected_action=sgt["expected_action"],
            acceptable_actions=frozenset(sgt["acceptable_actions"]),
            expected_risk_level=sgt["expected_risk_level"],
            recovery_conditions=tuple(sgt["recovery_conditions"])
        )
        for sgt in plan["scenarios"]
    }

    adapter = OpsPilotLiveAdapter(ground_truths)

    all_trials = []
    async def clear_db():
        conn = await asyncpg.connect(adapter.db_url)
        await conn.execute("UPDATE incidents SET status = 'FAILED' WHERE status NOT IN ('RESOLVED', 'FAILED', 'ESCALATED')")
        await conn.close()
        
        print("Rebuilding Qdrant knowledge index for benchmark collection...")
        async with SessionLocal() as session:
            count = await RAGService(session).rebuild_knowledge_index()
            print(f"Indexed {count} points into Qdrant benchmark collection.")

    asyncio.run(clear_db())

    print("Executing BASELINE trials...")
    all_trials.extend(execute_trials(config, adapter, "BASELINE"))
    
    print("\nExecuting OPSPILOT trials...")
    all_trials.extend(execute_trials(config, adapter, "OPSPILOT"))

    out_data = {
        "trials": [trial.to_dict() for trial in all_trials]
    }
    
    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)
    
    print(f"\nExecution complete. Saved {len(all_trials)} trial records to {args.output_file}")

if __name__ == "__main__":
    main()
