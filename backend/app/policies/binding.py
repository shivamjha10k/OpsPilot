from __future__ import annotations

import hashlib
import json
import uuid

from app.models.domain import Environment, RiskLevel


def action_fingerprint(*, incident_id: uuid.UUID, action_type: str, parameters: dict,
                       environment: Environment, risk_level: RiskLevel,
                       policy_id: uuid.UUID | None, policy_version: str | None) -> str:
    payload = {
        "incident_id": str(incident_id),
        "action_type": action_type,
        "parameters": parameters,
        "environment": environment.value,
        "risk_level": risk_level.value,
        "policy_id": str(policy_id) if policy_id else None,
        "policy_version": policy_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
