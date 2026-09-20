from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RestartServiceInput(ToolInput):
    service_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=500)


class ScaleServiceInput(ToolInput):
    service_id: uuid.UUID
    desired_replicas: int = Field(ge=1, le=1000)


class RollbackDeploymentInput(ToolInput):
    service_id: uuid.UUID
    deployment_id: uuid.UUID


class ClearCacheInput(ToolInput):
    service_id: uuid.UUID


class ScaleWorkersInput(ToolInput):
    service_id: uuid.UUID
    desired_workers: int = Field(ge=1, le=1000)


class ToolExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    tool: str
    service_id: uuid.UUID | None = None
    execution_id: uuid.UUID
    message: str
    state_before: dict[str, Any] | None = None
    state_after: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolFailureResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = False
    tool: str
    execution_id: uuid.UUID
    error_code: str
    message: str
    retryable: bool = False
