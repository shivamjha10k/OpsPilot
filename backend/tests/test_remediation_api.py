import os
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.database import get_db_session
from app.main import app
from app.services.auth_service import create_access_token
from app.models.domain import Approval, ApprovalStatus, Environment, Incident, IncidentStatus, RemediationAction, RemediationStatus, RiskLevel, Service, ServiceStatus, Severity
from app.models.user import Role, User

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="set TEST_DATABASE_URL to run integration tests")

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


async def setup_data(session: AsyncSession):
    user = User(name="Engineer", email=f"eng-{uuid.uuid4()}@example.com", password_hash="test", role=Role.ENGINEER)
    service = Service(name=f"svc-{uuid.uuid4().hex[:6]}", description="test", environment=Environment.STAGING, status=ServiceStatus.HEALTHY, owner=user)
    session.add(service)
    await session.flush()
    
    incident = Incident(
        incident_number=f"INC-{uuid.uuid4().hex[:8].upper()}",
        title="Test Incident",
        description="test",
        service_id=service.id,
        severity=Severity.HIGH,
        status=IncidentStatus.DETECTED,
        detected_at=datetime.now(timezone.utc)
    )
    session.add(incident)
    await session.commit()
    return user, incident

@pytest.mark.asyncio
async def test_remediation_api_serialization_without_approval(session: AsyncSession, monkeypatch):
    user, incident = await setup_data(session)
    
    # We create a RemediationAction manually that has no approval (e.g. ALLOW policy)
    action = RemediationAction(
        incident_id=incident.id,
        action_type="restart_service",
        parameters={"service_id": str(incident.service_id)},
        risk_level=RiskLevel.MEDIUM,
        status=RemediationStatus.PENDING,
        requested_by=user.id,
        idempotency_key=str(uuid.uuid4()),
        requested_at=datetime.now(timezone.utc),
        environment=Environment.STAGING,
        policy_decision="ALLOW"
    )
    session.add(action)
    await session.commit()
    
    factory = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
    async def override_session():
        async with factory() as request_session:
            yield request_session

    app.dependency_overrides[get_db_session] = override_session
    token = create_access_token(user.id, get_settings())
    
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/remediation/{action.id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["approval_id"] is None
            assert data["id"] == str(action.id)
            
            # Now test requesting the same idempotency key (simulating a retry which returns existing)
            # This would hit gateway.request and then return existing action.
            response_retry = await client.post(
                f"/api/v1/incidents/{incident.id}/remediation",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "action_type": "restart_service",
                    "parameters": {"service_id": str(incident.service_id)},
                    "idempotency_key": action.idempotency_key
                }
            )
            # if ToolGateway throws error or loads successfully
            assert response_retry.status_code == 202
            assert response_retry.json()["data"]["approval_id"] is None
            
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio
async def test_remediation_api_serialization_with_approval(session: AsyncSession, monkeypatch):
    user, incident = await setup_data(session)
    
    action = RemediationAction(
        incident_id=incident.id,
        action_type="restart_service",
        parameters={"service_id": str(incident.service_id)},
        risk_level=RiskLevel.HIGH,
        status=RemediationStatus.APPROVAL_REQUIRED,
        requested_by=user.id,
        idempotency_key=str(uuid.uuid4()),
        requested_at=datetime.now(timezone.utc),
        environment=Environment.PRODUCTION,
        policy_decision="REQUIRE_APPROVAL"
    )
    session.add(action)
    await session.flush()
    
    approval = Approval(
        remediation_action_id=action.id,
        requested_by=user.id,
        status=ApprovalStatus.PENDING,
        expires_at=datetime.now(timezone.utc)
    )
    session.add(approval)
    await session.commit()
    
    factory = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
    async def override_session():
        async with factory() as request_session:
            yield request_session

    app.dependency_overrides[get_db_session] = override_session
    token = create_access_token(user.id, get_settings())
    
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/remediation/{action.id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["approval_id"] == str(approval.id)
            assert data["id"] == str(action.id)
            
            response_retry = await client.post(
                f"/api/v1/incidents/{incident.id}/remediation",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "action_type": "restart_service",
                    "parameters": {"service_id": str(incident.service_id)},
                    "idempotency_key": action.idempotency_key
                }
            )
            assert response_retry.status_code == 202
            assert response_retry.json()["data"]["approval_id"] == str(approval.id)
            
    finally:
        app.dependency_overrides.pop(get_db_session, None)
