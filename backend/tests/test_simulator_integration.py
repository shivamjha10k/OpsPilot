import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.database import Base, get_db_session
from app.main import app
from app.models.domain import (
    Alert, Deployment, DeploymentStatus, Environment, Event, Incident, IncidentStatus, Log, Metric, Service,
    ServiceStatus, SimulationRun, SimulationStatus,
)
from app.models.user import Role, User
from app.services.auth_service import create_access_token
from app.simulator.manager import SimulatorManager

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="set TEST_DATABASE_URL to run simulator integration tests")


@pytest_asyncio.fixture
async def session(safe_test_engine):
    async with safe_test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(safe_test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    async with safe_test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)



async def setup(session: AsyncSession) -> tuple[dict[str, Service], User, User]:
    engineer = User(name="Simulator Engineer", email=f"sim-eng-{uuid.uuid4()}@example.com", password_hash="test", role=Role.ENGINEER)
    viewer = User(name="Simulator Viewer", email=f"sim-view-{uuid.uuid4()}@example.com", password_hash="test", role=Role.VIEWER)
    names = ("payment-service", "order-service", "user-service", "notification-service", "search-service")
    services = {
        name: Service(name=name, description="simulated", environment=Environment.STAGING, status=ServiceStatus.HEALTHY)
        for name in names
    }
    session.add_all([engineer, viewer, *services.values()])
    await session.commit()
    return services, engineer, viewer


@pytest.mark.asyncio
async def test_db_exhaustion_flows_through_phase4_and_stop_preserves_data(session: AsyncSession) -> None:
    services, engineer, _ = await setup(session)
    manager = SimulatorManager()
    run = await manager.trigger(session, "db_connection_exhaustion", engineer)
    assert run.status is SimulationStatus.RUNNING
    assert run.current_state["metrics"]["db_connection_utilization"] == 99
    assert await session.scalar(select(func.count()).select_from(Metric)) >= 6
    assert await session.scalar(select(func.count()).select_from(Log)) == 1
    assert await session.scalar(select(func.count()).select_from(Event)) == 3
    assert await session.scalar(select(func.count()).select_from(Alert)) == 3
    incident = await session.scalar(select(Incident).options(selectinload(Incident.alerts)).where(Incident.service_id == services["payment-service"].id))
    assert incident is not None
    assert incident.status is IncidentStatus.DETECTED
    assert len(incident.alerts) == 3
    assert await session.scalar(select(func.count()).select_from(Deployment)) == 0

    stopped = await manager.stop(session, run.id, engineer)
    assert stopped.status is SimulationStatus.STOPPED
    refreshed_incident = await session.scalar(select(Incident).where(Incident.id == incident.id))
    assert refreshed_incident.status is IncidentStatus.DETECTED
    assert await session.scalar(select(func.count()).select_from(Event)) == 3


@pytest.mark.asyncio
async def test_failed_deployment_persists_deployment_and_degradation(session: AsyncSession) -> None:
    services, engineer, _ = await setup(session)
    run = await SimulatorManager().trigger(session, "failed_deployment", engineer)
    deployment = await session.scalar(select(Deployment).where(Deployment.service_id == services["order-service"].id))
    assert deployment is not None
    assert deployment.status is DeploymentStatus.FAILED
    assert deployment.version == "v2.9.0"
    assert run.current_state["version"] == "v2.9.0"
    assert run.current_state["state"] == "FAILED"


@pytest.mark.asyncio
async def test_simulator_api_rbac_and_pipeline(session: AsyncSession) -> None:
    services, engineer, viewer = await setup(session)
    factory = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)

    async def override_session():
        async with factory() as request_session:
            yield request_session

    app.dependency_overrides[get_db_session] = override_session
    settings = get_settings()
    engineer_token = create_access_token(engineer.id, settings)
    viewer_token = create_access_token(viewer.id, settings)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            scenarios = await client.get("/api/v1/simulator/scenarios", headers={"Authorization": f"Bearer {viewer_token}"})
            assert scenarios.status_code == 200
            denied = await client.post("/api/v1/simulator/scenarios/high_cpu/trigger",
                                       headers={"Authorization": f"Bearer {viewer_token}"}, json={})
            assert denied.status_code == 403
            triggered = await client.post("/api/v1/simulator/scenarios/high_cpu/trigger",
                                          headers={"Authorization": f"Bearer {engineer_token}"}, json={})
            assert triggered.status_code == 201
            simulation_id = triggered.json()["data"]["id"]
            stopped = await client.post(f"/api/v1/simulator/simulations/{simulation_id}/stop",
                                        headers={"Authorization": f"Bearer {engineer_token}"})
            assert stopped.status_code == 200
            assert stopped.json()["data"]["status"] == "STOPPED"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
