import uuid
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.ai.context import IncidentContextBuilder
from app.models.domain import Incident, Service, Log, Environment, Severity, IncidentStatus
from app.core.config import Settings
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
async def test_incident_context_builder_filters_historical_logs(session: AsyncSession) -> None:
    settings = Settings(incident_correlation_window_minutes=5)
    
    service_id = uuid.uuid4()
    service = Service(id=service_id, name="test-service", environment=Environment.PRODUCTION)
    session.add(service)

    now = datetime.now(timezone.utc)
    
    incident_id = uuid.uuid4()
    incident = Incident(
        id=incident_id,
        service_id=service_id,
        incident_number="INC-123",
        title="High CPU",
        description="CPU spiked",
        severity=Severity.HIGH,
        status=IncidentStatus.DETECTED,
        detected_at=now
    )
    session.add(incident)
    
    # Old DB connection log (yesterday)
    log1 = Log(id=1, service_id=service_id, message="connection pool exhausted", occurred_at=now - timedelta(days=1), level="INFO")
    # Current CPU log
    log2 = Log(id=2, service_id=service_id, message="CPU utilization exceeded threshold", occurred_at=now - timedelta(minutes=2), level="INFO")
    
    session.add_all([log1, log2])
    await session.commit()
    
    builder = IncidentContextBuilder(session, settings)
    context = await builder.build(incident_id)
    
    logs = context["logs"]
    assert len(logs) == 1
    assert "CPU" in logs[0]["message"]
    
    # Verify the old DB connection log is not in untrusted data
    untrusted = context["untrusted_operational_data"]["logs"]
    assert len(untrusted) == 1
    assert "CPU" in untrusted[0]["message"]
