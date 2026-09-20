from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.domain import Environment, RiskLevel


class PolicyDecision(str, enum.Enum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


class PolicyDecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: PolicyDecision
    action_type: str
    environment: Environment | str
    risk_level: RiskLevel
    matched_policy_id: uuid.UUID | None = None
    matched_policy_name: str | None = None
    reason: str
    approval_required: bool
    policy_version: str | None = None
    evaluated_at: datetime
