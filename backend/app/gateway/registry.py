from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from app.models.domain import Environment, RiskLevel
from app.models.user import Role
from app.gateway.schemas import (
    ClearCacheInput, RestartServiceInput, RollbackDeploymentInput, ScaleServiceInput, ScaleWorkersInput,
)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type
    risk_level: RiskLevel
    required_roles: frozenset[Role]
    allowed_environments: frozenset[Environment]
    mutating: bool
    idempotent: bool
    handler: Callable

    def metadata(self) -> dict:
        return {"name": self.name, "description": self.description, "risk_level": self.risk_level.value,
                "required_roles": sorted(role.value for role in self.required_roles),
                "allowed_environments": sorted(environment.value for environment in self.allowed_environments),
                "mutating": self.mutating, "idempotent": self.idempotent,
                "input_schema": self.input_model.model_json_schema()}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"unknown tool: {name}") from exc

    def list_metadata(self) -> list[dict]:
        return [self._tools[name].metadata() for name in sorted(self._tools)]


def build_tool_registry(manager=None) -> ToolRegistry:
    if manager is None:
        from app.simulator.manager import get_simulator_manager
        manager = get_simulator_manager()
    registry = ToolRegistry()
    roles = frozenset({Role.ENGINEER, Role.ADMIN})
    environments = frozenset({Environment.DEVELOPMENT, Environment.STAGING, Environment.PRODUCTION})
    registry.register(ToolDefinition("restart_service", "Restart a simulated service", RestartServiceInput, RiskLevel.LOW, roles, environments, True, True, manager.restart_service))
    registry.register(ToolDefinition("scale_service", "Scale simulated service replicas", ScaleServiceInput, RiskLevel.MEDIUM, roles, environments, True, True, manager.scale_service))
    registry.register(ToolDefinition("rollback_deployment", "Roll back a failed simulated deployment", RollbackDeploymentInput, RiskLevel.HIGH, roles, environments, True, True, manager.rollback_deployment))
    registry.register(ToolDefinition("clear_cache", "Clear a simulated service cache", ClearCacheInput, RiskLevel.LOW, roles, environments, True, True, manager.clear_cache))
    registry.register(ToolDefinition("scale_workers", "Scale a simulated worker pool", ScaleWorkersInput, RiskLevel.MEDIUM, roles, environments, True, True, manager.scale_workers))
    return registry
