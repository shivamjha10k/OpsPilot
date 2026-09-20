import uuid
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.gateway.registry import ToolRegistry, build_tool_registry
from app.models.domain import Environment, RiskLevel
from app.models.user import Role, User
from app.policies.engine import PolicyEngine
from app.policies.schemas import PolicyDecision


class EmptyPolicyResult:
    def all(self) -> list:
        return []


def make_user(*, active: bool = True, role: Role = Role.ENGINEER) -> User:
    return User(
        id=uuid.uuid4(),
        name="Policy Tester",
        email=f"{uuid.uuid4()}@example.com",
        password_hash="test-only",
        role=role,
        is_active=active,
    )


def empty_policy_session() -> AsyncMock:
    session = AsyncMock()
    session.scalars.return_value = EmptyPolicyResult()
    return session


@pytest.mark.asyncio
async def test_unknown_action_is_denied() -> None:
    result = await PolicyEngine().evaluate_action(
        AsyncMock(), action_type="unknown", environment=Environment.DEVELOPMENT,
        risk_level=RiskLevel.LOW, actor=make_user(), parameters={},
        registry=build_tool_registry(),
    )

    assert result.decision is PolicyDecision.DENY


@pytest.mark.asyncio
async def test_critical_risk_is_denied_before_policy_lookup() -> None:
    result = await PolicyEngine().evaluate_action(
        AsyncMock(), action_type="restart_service", environment=Environment.DEVELOPMENT,
        risk_level=RiskLevel.CRITICAL, actor=make_user(), parameters={},
        registry=build_tool_registry(),
    )

    assert result.decision is PolicyDecision.DENY
    assert "Critical" in result.reason


@pytest.mark.asyncio
async def test_disallowed_environment_is_denied() -> None:
    source = build_tool_registry()
    registry = ToolRegistry()
    registry.register(replace(
        source.get("restart_service"),
        allowed_environments=frozenset({Environment.DEVELOPMENT}),
    ))

    result = await PolicyEngine().evaluate_action(
        AsyncMock(), action_type="restart_service", environment=Environment.PRODUCTION,
        risk_level=RiskLevel.LOW, actor=make_user(), parameters={}, registry=registry,
    )

    assert result.decision is PolicyDecision.DENY


@pytest.mark.asyncio
async def test_inactive_actor_is_denied() -> None:
    result = await PolicyEngine().evaluate_action(
        AsyncMock(), action_type="restart_service", environment=Environment.DEVELOPMENT,
        risk_level=RiskLevel.LOW, actor=make_user(active=False), parameters={},
        registry=build_tool_registry(),
    )

    assert result.decision is PolicyDecision.DENY


@pytest.mark.asyncio
async def test_registry_risk_overrides_lower_caller_risk() -> None:
    result = await PolicyEngine().evaluate_action(
        empty_policy_session(), action_type="rollback_deployment", environment=Environment.STAGING,
        risk_level=RiskLevel.LOW, actor=make_user(), parameters={},
        registry=build_tool_registry(),
    )

    assert result.decision is PolicyDecision.DENY
    assert result.risk_level is RiskLevel.HIGH