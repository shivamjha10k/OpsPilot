import uuid
import pytest
from app.ai.tools import search_logs, _events, get_service_metrics, LogsInput, LimitedServiceInput, MetricsInput
from app.models.domain import Log, Event, Metric, Service, Incident, Environment
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import Base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import os

from tests.conftest import TEST_DATABASE_URL, validate_test_database_url

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="set TEST_DATABASE_URL to run integration tests")

import pytest_asyncio

@pytest_asyncio.fixture
async def session(safe_test_engine):
    async with safe_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(safe_test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with safe_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.mark.asyncio
async def test_search_logs_filters_by_start_and_end_time(session: AsyncSession) -> None:
    service_id = uuid.uuid4()
    service = Service(id=service_id, name="test-service", environment=Environment.PRODUCTION)
    session.add(service)

    now = datetime.now(timezone.utc)
    
    # Excluded (before start)
    log1 = Log(id=1, service_id=service_id, message="log1", occurred_at=now - timedelta(minutes=10), level="INFO")
    # Included
    log2 = Log(id=2, service_id=service_id, message="log2", occurred_at=now - timedelta(minutes=5), level="INFO")
    # Excluded (after end)
    log3 = Log(id=3, service_id=service_id, message="log3", occurred_at=now + timedelta(minutes=10), level="INFO")
    
    session.add_all([log1, log2, log3])
    await session.commit()
    
    start_time = now - timedelta(minutes=7)
    end_time = now
    
    args = LogsInput(service_id=service_id, start_time=start_time, end_time=end_time)
    results = await search_logs(session, args)
    
    assert len(results) == 1
    assert results[0]["message"] == "log2"

@pytest.mark.asyncio
async def test_get_recent_events_filters_by_start_and_end_time(session: AsyncSession) -> None:
    service_id = uuid.uuid4()
    service = Service(id=service_id, name="test-service2", environment=Environment.PRODUCTION)
    session.add(service)

    now = datetime.now(timezone.utc)
    
    evt1 = Event(id=uuid.uuid4(), event_id="evt-1", service_id=service_id, event_type="test1", source="test", payload={}, occurred_at=now - timedelta(minutes=10))
    evt2 = Event(id=uuid.uuid4(), event_id="evt-2", service_id=service_id, event_type="test2", source="test", payload={}, occurred_at=now - timedelta(minutes=5))
    evt3 = Event(id=uuid.uuid4(), event_id="evt-3", service_id=service_id, event_type="test3", source="test", payload={}, occurred_at=now + timedelta(minutes=10))
    
    session.add(evt1)
    session.add(evt2)
    session.add(evt3)
    await session.commit()
    
    start_time = now - timedelta(minutes=7)
    end_time = now
    
    args = LimitedServiceInput(service_id=service_id, start_time=start_time, end_time=end_time)
    results = await _events(session, args)
    
    assert len(results) == 1
    assert results[0]["description"] == "test2"

@pytest.mark.asyncio
async def test_get_service_metrics_filters_by_start_and_end_time(session: AsyncSession) -> None:
    service_id = uuid.uuid4()
    service = Service(id=service_id, name="test-service3", environment=Environment.PRODUCTION)
    session.add(service)

    now = datetime.now(timezone.utc)
    
    met1 = Metric(id=1, service_id=service_id, metric_name="cpu", value=10.0, occurred_at=now - timedelta(minutes=10))
    met2 = Metric(id=2, service_id=service_id, metric_name="cpu", value=20.0, occurred_at=now - timedelta(minutes=5))
    met3 = Metric(id=3, service_id=service_id, metric_name="cpu", value=30.0, occurred_at=now + timedelta(minutes=10))
    
    session.add(met1)
    session.add(met2)
    session.add(met3)
    await session.commit()
    
    start_time = now - timedelta(minutes=7)
    end_time = now
    
    args = MetricsInput(service_id=service_id, metric_name="cpu", start_time=start_time, end_time=end_time)
    results = await get_service_metrics(session, args)
    
    assert len(results) == 1
    assert results[0]["value"] == 20.0
