import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.database import get_db_session
from app.main import app
from app.services.auth_service import create_access_token
from app.models.domain import AuditLog, Environment, Event, EventProcessingStatus, Incident, IncidentStatus, Service, ServiceStatus, Severity
from app.models.user import Role, User
from app.services.incident_engine import IncidentEngine

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="set TEST_DATABASE_URL to run Phase 4 integration tests")


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



def now() -> datetime:
    return datetime.now(timezone.utc)


async def setup_service(session: AsyncSession, name: str = "payment-service") -> tuple[Service, User]:
    user = User(name="Engineer", email=f"engineer-{uuid.uuid4()}@example.com", password_hash="test", role=Role.ENGINEER)
    service = Service(name=f"{name}-{uuid.uuid4().hex[:6]}", description="test", environment=Environment.STAGING,
                      status=ServiceStatus.HEALTHY, owner=user)
    session.add(service)
    await session.commit()
    return service, user


def event(service_id: uuid.UUID, event_id: str, occurred_at: datetime, event_type: str = "metric.alert") -> Event:
    return Event(event_id=event_id, event_type=event_type, source="test", service_id=service_id,
                 payload={"metric": "cpu_usage", "value": 95, "severity": "HIGH"}, occurred_at=occurred_at)


@pytest.mark.asyncio
async def test_ingestion_is_idempotent_and_correlates_alerts(session: AsyncSession) -> None:
    service, actor = await setup_service(session)
    first = await IncidentEngine(session).ingest(event(service.id, "evt-1", now()), actor)
    duplicate = await IncidentEngine(session).ingest(event(service.id, "evt-1", now()), actor)
    second = await IncidentEngine(session).ingest(event(service.id, "evt-2", now() + timedelta(minutes=1), "error_rate.spike"), actor)

    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert second.incident.id == first.incident.id
    assert await session.scalar(select(func.count()).select_from(Event)) == 2
    assert await session.scalar(select(func.count()).select_from(Incident)) == 1


@pytest.mark.asyncio
async def test_correlation_window_and_service_boundary(session: AsyncSession) -> None:
    service_a, actor = await setup_service(session, "service-a")
    service_b, _ = await setup_service(session, "service-b")
    first = await IncidentEngine(session).ingest(event(service_a.id, "evt-a", now()), actor)
    outside = await IncidentEngine(session).ingest(event(service_a.id, "evt-b", now() + timedelta(minutes=6)), actor)
    different = await IncidentEngine(session).ingest(event(service_b.id, "evt-c", now() + timedelta(minutes=1)), actor)
    assert outside.incident.id != first.incident.id
    assert different.incident.id != first.incident.id


@pytest.mark.asyncio
async def test_acknowledge_assign_escalate_and_audit(session: AsyncSession) -> None:
    service, actor = await setup_service(session)
    result = await IncidentEngine(session).ingest(event(service.id, "evt-lifecycle", now()), actor)
    incident = await IncidentEngine(session).acknowledge(result.incident.id, actor)
    assert incident.status is IncidentStatus.ACKNOWLEDGED
    assert incident.acknowledged_at is not None
    await IncidentEngine(session).acknowledge(incident.id, actor)
    incident = await IncidentEngine(session).assign(incident.id, actor.id, actor)
    assert incident.assigned_to == actor.id
    incident = await IncidentEngine(session).escalate(incident.id, actor)
    assert incident.status is IncidentStatus.ESCALATED
    audit_count = await session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.resource_id == str(incident.id)))
    assert audit_count >= 4


@pytest.mark.asyncio
async def test_incident_api_ingestion_listing_timeline_and_rbac(session: AsyncSession, monkeypatch) -> None:
    service, engineer = await setup_service(session, "api-service")
    viewer = User(name="Viewer", email=f"viewer-{uuid.uuid4()}@example.com", password_hash="test", role=Role.VIEWER)
    session.add(viewer)
    await session.commit()
    factory = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)

    async def override_session():
        async with factory() as request_session:
            yield request_session

    app.dependency_overrides[get_db_session] = override_session
    monkeypatch.setattr(
        "app.api.v1.events.process_event_task.apply_async",
        lambda *args, **kwargs: SimpleNamespace(id="test-task-id"),
    )
    settings = get_settings()
    engineer_token = create_access_token(engineer.id, settings)
    viewer_token = create_access_token(viewer.id, settings)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/events",
                headers={"Authorization": f"Bearer {engineer_token}"},
                json={
                    "event_id": "api-event-1", "event_type": "health.alert", "source": "api-test",
                    "service_id": str(service.id), "payload": {"message": "health check failed"},
                    "occurred_at": now().isoformat(),
                },
            )
            assert response.status_code == 202
            assert response.json()["data"]["status"] == "QUEUED"
            assert response.json()["data"]["task_id"] == "test-task-id"
            listed = await client.get("/api/v1/incidents", headers={"Authorization": f"Bearer {engineer_token}"})
            assert listed.status_code == 200
            assert listed.json()["pagination"]["total"] == 0
            denied = await client.post(
                "/api/v1/incidents",
                headers={"Authorization": f"Bearer {viewer_token}"},
                json={"title": "Denied", "description": "Denied", "service_id": str(service.id), "severity": "HIGH"},
            )
            assert denied.status_code == 403
            monkeypatch.setattr(
                "app.api.v1.events.process_event_task.apply_async",
                lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("redis unavailable")),
            )
            unavailable = await client.post(
                "/api/v1/events",
                headers={"Authorization": f"Bearer {engineer_token}"},
                json={
                    "event_id": "api-event-queue-failure", "event_type": "metric.alert", "source": "api-test",
                    "service_id": str(service.id), "payload": {"metric": "cpu_usage", "severity": "HIGH"},
                    "occurred_at": now().isoformat(),
                },
            )
            assert unavailable.status_code == 503
            failed_event = await session.scalar(select(Event).where(Event.event_id == "api-event-queue-failure"))
            assert failed_event.processing_status is EventProcessingStatus.FAILED
    finally:
        app.dependency_overrides.pop(get_db_session, None)
