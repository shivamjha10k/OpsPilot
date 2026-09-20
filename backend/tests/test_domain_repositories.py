import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.domain import (
    Alert,
    Environment,
    Incident,
    IncidentStatus,
    Service,
    ServiceStatus,
    Severity,
)
from app.models.user import Role, User
from app.repositories.alert_repository import AlertRepository
from app.repositories.event_repository import EventRepository
from app.repositories.incident_repository import IncidentRepository
from app.repositories.service_repository import ServiceRepository
from app.models.domain import Event


TEST_DATABASE_URL = __import__("os").environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="set TEST_DATABASE_URL to run PostgreSQL repository integration tests",
)


@pytest_asyncio.fixture
async def session(safe_test_engine):
    async with safe_test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(safe_test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session
    async with safe_test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)



def now() -> datetime:
    return datetime.now(timezone.utc)


async def create_service(session: AsyncSession) -> Service:
    user = User(
        name="Repository Owner",
        email=f"owner-{uuid.uuid4()}@example.com",
        password_hash="test-only",
        role=Role.ENGINEER,
    )
    service = Service(
        name=f"service-{uuid.uuid4()}",
        description="Repository test service",
        environment=Environment.STAGING,
        status=ServiceStatus.HEALTHY,
        owner=user,
    )
    session.add(service)
    await session.commit()
    return service


@pytest.mark.asyncio
async def test_repository_crud_filtering_pagination_and_relationships(session: AsyncSession) -> None:
    service = await create_service(session)
    event = Event(
        event_id=f"event-{uuid.uuid4()}",
        event_type="health.alert",
        source="test",
        service_id=service.id,
        payload={"healthy": False},
        occurred_at=now(),
    )
    alert = Alert(
        service_id=service.id,
        source="test",
        alert_type="latency",
        severity=Severity.HIGH,
        message="Latency exceeded threshold",
        payload={"p95_ms": 900},
        occurred_at=now(),
    )
    incident = Incident(
        incident_number=f"INC-{uuid.uuid4().hex[:8].upper()}",
        title="Repository test incident",
        description="Created for repository coverage",
        service_id=service.id,
        severity=Severity.HIGH,
        status=IncidentStatus.DETECTED,
        detected_at=now(),
    )
    incident.alerts.append(alert)
    session.add_all([event, incident])
    await session.commit()

    assert (await ServiceRepository(session).get_by_name(service.name)).id == service.id
    assert (await EventRepository(session).get_by_event_id(event.event_id)).payload == {"healthy": False}
    alert_page = await AlertRepository(session).list_by_service(service.id, page=1, page_size=10)
    incident_page = await IncidentRepository(session).list(
        service_id=service.id, severity=Severity.HIGH, page=1, page_size=10
    )
    assert alert_page.total == 1
    assert incident_page.total == 1
    assert incident_page.items[0].alerts[0].message == alert.message


@pytest.mark.asyncio
async def test_event_id_is_database_unique(session: AsyncSession) -> None:
    service = await create_service(session)
    event_id = f"duplicate-{uuid.uuid4()}"
    repository = EventRepository(session)
    await repository.create(
        Event(
            event_id=event_id,
            event_type="test",
            source="test",
            service_id=service.id,
            payload={"attempt": 1},
            occurred_at=now(),
        )
    )
    await session.commit()
    with pytest.raises(IntegrityError):
        await repository.create(
            Event(
                event_id=event_id,
                event_type="test",
                source="test",
                service_id=service.id,
                payload={"attempt": 2},
                occurred_at=now(),
            )
        )
    await session.rollback()
