import asyncio
import httpx
import asyncpg
import time

BASE_URL = "http://localhost:8000/api/v1"

async def main():
    print("Logging in...")
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE_URL}/auth/login", json={"email": "admin@opspilot.local", "password": "change-me-admin"})
        resp.raise_for_status()
        token = resp.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        print("Fetching payment-service...")
        conn = await asyncpg.connect("postgresql://opspilot:change-me-local-only@localhost:5433/opspilot")
        row = await conn.fetchrow("SELECT id FROM services WHERE name='payment-service'")
        service_id = row["id"]

        print("Creating autonomous E2E policy...")
        policy_payload = {
            "name": "E2E Autonomous Restart",
            "action_type": "restart_service",
            "environment": "PRODUCTION",
            "risk_level": "LOW",
            "requires_approval": False,
            "is_allowed": True
        }
        resp = await client.post(f"{BASE_URL}/policies", headers=headers, json=policy_payload)
        if resp.status_code not in (201, 409):  # 409 if it already exists
            print(f"Failed to create policy: {resp.status_code} - {resp.text}")
            resp.raise_for_status()
        
        print(f"Triggering simulator for service_id: {service_id}")
        resp = await client.post(f"{BASE_URL}/simulator/scenarios/high_cpu/trigger", 
                             headers=headers, 
                             json={"configuration": {"target_service_id": str(service_id)}})
        resp.raise_for_status()
        sim_data = resp.json()["data"]
        sim_id = sim_data["id"]
        print(f"Simulation triggered: {sim_id}")

        incident_id = None
        investigation_id = None
        
        print("Waiting for incident...")
        for _ in range(30):
            inc = await conn.fetchrow("SELECT id, status FROM incidents WHERE service_id=$1 ORDER BY created_at DESC LIMIT 1", service_id)
            if inc:
                incident_id = inc["id"]
                print(f"Incident created: {incident_id}")
                break
            await asyncio.sleep(2)

        if not incident_id:
            print("Incident not created.")
            return

        print("Waiting for investigation...")
        for _ in range(60):
            inv = await conn.fetchrow("SELECT id, status, root_cause, recommendation, evidence, confidence, risk_level FROM ai_investigations WHERE incident_id=$1 ORDER BY created_at DESC LIMIT 1", incident_id)
            if inv:
                investigation_id = inv["id"]
                print(f"Investigation Status: {inv['status']}")
                if inv["status"] in ("COMPLETED", "FAILED"):
                    print(f"Investigation Final Status: {inv['status']}")
                    print(f"Root cause: {inv['root_cause']}")
                    print(f"Recommended action: {inv['recommendation']}")
                    print(f"Confidence score: {inv['confidence']}")
                    print(f"Risk level: {inv['risk_level']}")
                    break
            await asyncio.sleep(2)
            
        print("Waiting for remediation action...")
        for _ in range(30):
            rem = await conn.fetchrow("SELECT id, status, policy_decision, environment FROM remediation_actions WHERE incident_id=$1 ORDER BY requested_at DESC LIMIT 1", incident_id)
            if rem and rem["status"] in ("COMPLETED", "FAILED", "APPROVAL_REQUIRED", "EXECUTING"):
                print(f"Remediation: {rem['id']} | Status: {rem['status']} | Policy: {rem['policy_decision']} | Env: {rem['environment']}")
                if rem["status"] in ("COMPLETED", "FAILED", "APPROVAL_REQUIRED"):
                    break
            await asyncio.sleep(2)
            
        print("Waiting for final incident state...")
        for _ in range(60):
            inc = await conn.fetchrow("SELECT id, status FROM incidents WHERE id=$1", incident_id)
            print(f"Current incident status: {inc['status']}")
            if inc["status"] in ("RESOLVED", "CLOSED", "FAILED"):
                break
            await asyncio.sleep(2)
        
        await asyncio.sleep(5)
        sim_status = await conn.fetchrow("SELECT status FROM simulation_runs WHERE id=$1", sim_id)
        print(f"Final Simulator Status: {sim_status['status']}")
        
        metrics = await conn.fetch("SELECT metric_name, value FROM metrics WHERE service_id=$1 ORDER BY occurred_at DESC LIMIT 10", service_id)
        print("Recent Metrics:")
        for m in metrics:
            print(f"Metric {m['metric_name']}: {m['value']}")
            
        initial_metrics = await conn.fetch("SELECT metric_name, value FROM metrics WHERE service_id=$1 ORDER BY occurred_at ASC LIMIT 10", service_id)
        print("Initial Metrics:")
        for m in initial_metrics:
            print(f"Metric {m['metric_name']}: {m['value']}")

        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
