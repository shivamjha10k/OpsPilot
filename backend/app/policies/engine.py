from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.registry import ToolRegistry
from app.models.domain import Environment, Policy, RemediationAction, RiskLevel
from app.models.user import Role, User

from .schemas import PolicyDecision, PolicyDecisionResult


class PolicyEngine:
    """Deterministic, database-backed policy evaluation for mutating tools."""

    async def evaluate_action(
        self,
        session: AsyncSession,
        *,
        action_type: str,
        environment: Environment | str,
        risk_level: RiskLevel,
        actor: User,
        parameters: dict,
        registry: ToolRegistry,
        incident_id: uuid.UUID | None = None,
        lock_policies: bool = False,
    ) -> PolicyDecisionResult:
        evaluated_at = datetime.now(timezone.utc)
        try:
            environment = Environment(environment)
        except ValueError:
            return self._result(PolicyDecision.DENY, action_type, environment, risk_level, None,
                                "Unknown environment", evaluated_at)
        try:
            tool = registry.get(action_type)
        except KeyError:
            return self._result(PolicyDecision.DENY, action_type, environment, risk_level, None,
                                "Unknown action is denied", evaluated_at)
        if environment not in tool.allowed_environments:
            return self._result(PolicyDecision.DENY, action_type, environment, risk_level, None,
                                "Action is not allowed in this environment", evaluated_at)
        if tool.risk_level is RiskLevel.CRITICAL or risk_level is RiskLevel.CRITICAL:
            return self._result(PolicyDecision.DENY, action_type, environment, RiskLevel.CRITICAL, None,
                                "Critical-risk actions are never executable", evaluated_at)
        if risk_level is not tool.risk_level:
            risk_level = tool.risk_level
        if not actor.is_active:
            return self._result(PolicyDecision.DENY, action_type, environment, risk_level, None,
                                "Inactive callers cannot execute actions", evaluated_at)
        if actor.role not in tool.required_roles:
            return self._result(PolicyDecision.DENY, action_type, environment, risk_level, None,
                                "Caller role is not authorized for this tool", evaluated_at)
        query = select(Policy).where(
            Policy.action_type.in_([action_type, "*"]),
            Policy.environment == environment,
            Policy.risk_level == risk_level,
        )
        if lock_policies:
            query = query.with_for_update()
        policies = list((await session.scalars(query)).all())
        if not policies:
            return self._result(PolicyDecision.DENY, action_type, environment, risk_level, None,
                                "No applicable policy exists", evaluated_at)
        # Explicit deny wins globally; otherwise action-specific, newer policy wins.
        policies.sort(key=lambda item: (
            0 if not item.is_allowed else 1,
            -(1 if item.action_type == action_type else 0),
            -(item.updated_at or item.created_at).timestamp(),
            str(item.id),
        ))
        # Deny wins first; within a decision, specific action and newest policy win.
        policy = policies[0]
        version = (policy.updated_at or policy.created_at).astimezone(timezone.utc).isoformat()
        if not policy.is_allowed:
            return self._result(PolicyDecision.DENY, action_type, environment, risk_level, policy,
                                "Matched policy denies this action", evaluated_at, version)
        if policy.max_frequency is not None:
            since = evaluated_at - timedelta(minutes=60)
            count = await session.scalar(select(func.count()).select_from(RemediationAction).where(
                RemediationAction.action_type == action_type,
                RemediationAction.environment == environment,
                RemediationAction.requested_at >= since,
                RemediationAction.status.not_in({"REJECTED", "CANCELLED"}),
            )) or 0
            if count >= policy.max_frequency:
                return self._result(PolicyDecision.DENY, action_type, environment, risk_level, policy,
                                    "Policy frequency limit exceeded", evaluated_at, version)
        decision = PolicyDecision.REQUIRE_APPROVAL if policy.requires_approval or risk_level in {RiskLevel.HIGH, RiskLevel.MEDIUM} else PolicyDecision.ALLOW
        return self._result(decision, action_type, environment, risk_level, policy,
                            "Policy requires human approval" if decision is PolicyDecision.REQUIRE_APPROVAL else "Policy allows action",
                            evaluated_at, version)

    @staticmethod
    def _result(decision: PolicyDecision, action_type: str, environment: Environment | str,
                risk_level: RiskLevel, policy: Policy | None, reason: str, evaluated_at: datetime,
                version: str | None = None) -> PolicyDecisionResult:
        return PolicyDecisionResult(
            decision=decision, action_type=action_type, environment=environment,
            risk_level=risk_level, matched_policy_id=policy.id if policy else None,
            matched_policy_name=policy.name if policy else None, reason=reason,
            approval_required=decision is PolicyDecision.REQUIRE_APPROVAL,
            policy_version=version, evaluated_at=evaluated_at,
        )
