from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AIProviderError(Exception):
    """Normalized provider failure that is safe to log without provider details."""


class AIOutputError(ValueError):
    """Provider output could not be validated as an investigation."""


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Evidence(BaseModel):
    source_type: str = Field(min_length=1, max_length=40)
    source_id: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2000)
    timestamp: datetime | None = None


class Observation(BaseModel):
    fact: str = Field(min_length=1, max_length=2000)
    source: str = Field(min_length=1, max_length=255)
    timestamp: datetime | None = None


class RootCause(BaseModel):
    cause: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(min_length=1, max_length=20)


class RecommendedAction(BaseModel):
    type: str = Field(min_length=1, max_length=120)
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=2000)


class InvestigationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=5000)
    observations: list[Observation] = Field(max_length=100)
    probable_root_causes: list[RootCause] = Field(max_length=20)
    recommended_action: RecommendedAction
    risk_level: RiskLevel
    requires_approval: bool
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(max_length=100)
    knowledge_citations: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("evidence")
    @classmethod
    def evidence_ids_are_unique(cls, value: list[Evidence]) -> list[Evidence]:
        ids = [(item.source_type, item.source_id) for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence entries must be unique")
        return value


class InvestigationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    incident_id: str
    model: str
    summary: str
    root_cause: str
    confidence: float
    evidence: dict
    recommendation: str
    recommendation_data: dict
    observations: list
    probable_root_causes: list
    knowledge_references: list
    risk_level: str
    requires_approval: bool
    status: str
    prompt_version: str
    duration_ms: int | None
    error_code: str | None
    task_id: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
