import uuid

import pytest
from pydantic import ValidationError

from app.gateway.registry import ToolRegistry, ToolDefinition, build_tool_registry
from app.gateway.schemas import RestartServiceInput, ScaleServiceInput
from app.models.domain import Environment, RiskLevel
from app.models.user import Role
from app.simulator.manager import get_simulator_manager


def test_gateway_registry_contains_only_explicit_simulator_tools():
    registry = build_tool_registry(get_simulator_manager())
    names = {item["name"] for item in registry.list_metadata()}
    assert names == {"restart_service", "scale_service", "rollback_deployment", "clear_cache", "scale_workers"}
    assert "handler" not in registry.list_metadata()[0]
    assert registry.get("rollback_deployment").risk_level is RiskLevel.HIGH
    assert registry.get("restart_service").required_roles == frozenset({Role.ENGINEER, Role.ADMIN})
    with pytest.raises(ValueError):
        registry.register(registry.get("restart_service"))


def test_gateway_inputs_are_strict_and_bounded():
    with pytest.raises(ValidationError):
        RestartServiceInput.model_validate({"service_id": "bad", "command": "rm -rf /"})
    with pytest.raises(ValidationError):
        ScaleServiceInput.model_validate({"service_id": str(uuid.uuid4()), "desired_replicas": 0})
    with pytest.raises(ValidationError):
        ScaleServiceInput.model_validate({"service_id": str(uuid.uuid4()), "desired_replicas": 2, "shell": "x"})


def test_tool_metadata_is_authoritative_and_simulator_only():
    registry = build_tool_registry(get_simulator_manager())
    for metadata in registry.list_metadata():
        assert metadata["mutating"] is True
        assert metadata["allowed_environments"] == sorted(item.value for item in Environment)
