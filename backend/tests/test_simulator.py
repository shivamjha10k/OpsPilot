from datetime import datetime, timezone
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.domain import Service, Environment, SimulationRun, SimulationStatus
from app.models.user import User
from app.simulator.manager import SERVICE_BASELINES, SimulatorManager
from app.simulator.scenarios import SCENARIOS
from app.simulator.state import SimulatedServiceState


def service(name: str) -> Service:
    return Service(id=uuid.uuid4(), name=name, description="test", environment=Environment.STAGING)


def test_all_scenarios_expose_structured_metadata() -> None:
    assert set(SCENARIOS) == {
        "high_cpu", "error_spike", "db_connection_exhaustion", "queue_backlog", "memory_leak", "failed_deployment",
    }
    for definition in SCENARIOS.values():
        metadata = definition.metadata()
        assert metadata["scenario"] == definition.name
        assert metadata["expected_root_cause"]
        assert metadata["expected_evidence"]
        assert metadata["recovery_conditions"]


def test_service_baselines_are_initialized_and_isolated() -> None:
    manager = SimulatorManager()
    payment = manager._state_for(service("payment-service"), datetime.now(timezone.utc))
    notification = manager._state_for(service("notification-service"), datetime.now(timezone.utc))
    assert payment.lifecycle is SimulatedServiceState.NORMAL
    assert payment.metrics["cpu_usage"] == SERVICE_BASELINES["payment-service"].cpu_usage
    assert "queue_depth" in notification.metrics
    assert payment.service_id != notification.service_id


def test_each_scenario_has_deterministic_failure_telemetry() -> None:
    manager = SimulatorManager()
    for name, definition in SCENARIOS.items():
        state = manager._state_for(service(definition.target_services[0]), datetime.now(timezone.utc))
        manager._apply_scenario(state, name, datetime.now(timezone.utc))
        events = manager._events_for(name, state, uuid.uuid4())
        assert state.lifecycle in {SimulatedServiceState.DEGRADED, SimulatedServiceState.FAILED}
        assert events
        assert all(payload.get("scenario") == name for _, payload in events)
        if name == "high_cpu":
            assert state.metrics["cpu_usage"] > 90
        if name == "db_connection_exhaustion":
            assert state.metrics["db_connection_utilization"] >= 98
        if name == "queue_backlog":
            assert state.metrics["queue_depth"] > 0
        if name == "memory_leak":
            assert state.metrics["memory_usage"] > 70


@pytest.mark.asyncio
async def test_simulation_stop_resets_state() -> None:
    manager = SimulatorManager()
    target_service = service("payment-service")
    
    # 1. Start with clean state
    state = manager._state_for(target_service, datetime.now(timezone.utc))
    assert state.lifecycle == SimulatedServiceState.NORMAL
    assert state.version == "v1.0.0"
    
    # 2. Mutate state simulating "failed_deployment"
    manager._apply_scenario(state, "failed_deployment", datetime.now(timezone.utc))
    assert state.lifecycle == SimulatedServiceState.FAILED
    assert state.version == "v2.9.0"
    assert state.metrics["error_rate"] == 0.22
    
    # Mocking DB and user
    session = AsyncMock()
    actor = User(id=uuid.uuid4(), email="test@test.com", password_hash="hash")
    
    # 3. Create active SimulationRun mock
    run_id = uuid.uuid4()
    run = SimulationRun(
        id=run_id,
        scenario="failed_deployment",
        target_service_id=target_service.id,
        target_service=target_service,
        status=SimulationStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    
    # Mock _get_run to return our run
    manager._get_run = AsyncMock(return_value=run)
    # Add to active runs
    manager._active.add(run.id)
    
    # 4. Stop simulation
    await manager.stop(session, run_id, actor)
    
    # 5. Verify the state is reset
    assert run.status == SimulationStatus.STOPPED
    assert state.lifecycle == SimulatedServiceState.NORMAL
    assert state.version == "v1.0.0"
    assert state.tick_count == 0
    assert state.replicas == 1
    assert state.workers == 1
    assert state.cache_generation == 0
    
    # Check baseline metrics restored
    assert state.metrics["error_rate"] == SERVICE_BASELINES["payment-service"].error_rate


@pytest.mark.asyncio
async def test_simulation_recovery_on_restart() -> None:
    manager = SimulatorManager()
    target_service = service("order-service")
    
    # Simulate an orphaned/stale RUNNING run
    # 1. Mutate the target service state to represent dirty persistence
    state = manager._state_for(target_service, datetime.now(timezone.utc))
    manager._apply_scenario(state, "db_connection_exhaustion", datetime.now(timezone.utc))
    target_service.simulation_state = state.snapshot()
    assert state.lifecycle == SimulatedServiceState.DEGRADED
    
    # 2. Mock a DB session where `SimulationRun` is RUNNING
    session = AsyncMock()
    run_id = uuid.uuid4()
    run = SimulationRun(
        id=run_id,
        scenario="db_connection_exhaustion",
        target_service_id=target_service.id,
        target_service=target_service,
        status=SimulationStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    
    # Mock scalars().all() to return our stale run
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [run]
    session.scalars.return_value = mock_scalars
    
    # 3. Trigger recovery (Simulates app startup)
    await manager.recover_stale_runs(session)
    
    # 4. Verify recovery behavior
    assert run.status == SimulationStatus.FAILED
    assert run.result.get("error") == "aborted_due_to_restart"
    
    # 5. Verify the service is returned to healthy baseline
    recovered_state = manager._state_for(target_service, datetime.now(timezone.utc))
    assert recovered_state.lifecycle == SimulatedServiceState.NORMAL
    assert recovered_state.version == "v1.0.0"
    assert recovered_state.tick_count == 0
    assert target_service.simulation_state["state"] == "NORMAL"
    assert target_service.simulation_state["metrics"]["error_rate"] == SERVICE_BASELINES["order-service"].error_rate
    
    # 6. Verify audit log was added
    assert session.add.call_count > 0
    added_obj = session.add.call_args[0][0]
    # We check if the last added object is AuditLog
    assert added_obj.__class__.__name__ == "AuditLog"
    assert added_obj.action == "SIMULATION_RECOVERED_ON_RESTART"
    assert added_obj.resource_id == str(run.id)
