from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.core.database import get_db_session
from app.core.errors import AppError
from app.gateway.registry import build_tool_registry
from app.models.domain import Environment, Policy, RiskLevel
from app.models.user import Role, User

router = APIRouter(prefix="/policies", tags=["policies"])


class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    action_type: str = Field(min_length=1, max_length=120)
    environment: Environment
    risk_level: RiskLevel
    requires_approval: bool = True
    is_allowed: bool = True
    max_frequency: int | None = Field(default=None, ge=1, le=100000)
    configuration: dict = Field(default_factory=dict)


class PolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    action_type: str | None = Field(default=None, min_length=1, max_length=120)
    environment: Environment | None = None
    risk_level: RiskLevel | None = None
    requires_approval: bool | None = None
    is_allowed: bool | None = None
    max_frequency: int | None = Field(default=None, ge=1, le=100000)
    configuration: dict | None = None


def _read(policy: Policy) -> dict:
    return {"id": str(policy.id), "name": policy.name, "action_type": policy.action_type,
            "environment": policy.environment.value, "risk_level": policy.risk_level.value,
            "requires_approval": policy.requires_approval, "is_allowed": policy.is_allowed,
            "max_frequency": policy.max_frequency, "configuration": policy.configuration or {},
            "created_by": str(policy.created_by), "created_at": policy.created_at, "updated_at": policy.updated_at}


def _validate_policy(payload: PolicyCreate | PolicyPatch, current: Policy | None = None) -> None:
    action_type = payload.action_type if payload.action_type is not None else current.action_type
    risk_level = payload.risk_level if payload.risk_level is not None else current.risk_level
    is_allowed = payload.is_allowed if payload.is_allowed is not None else (current.is_allowed if current else True)
    if action_type != "*":
        try:
            tool = build_tool_registry().get(action_type)
        except KeyError as exc:
            raise AppError("INVALID_POLICY_ACTION", "Policy action is not a registered tool", 422) from exc
        if risk_level is not tool.risk_level:
            raise AppError("INVALID_POLICY_RISK", "Policy risk must match the registered tool risk", 422)
    if risk_level is RiskLevel.CRITICAL and is_allowed:
        raise AppError("CRITICAL_POLICY_FORBIDDEN", "Critical actions can never be allowed", 422)


@router.get("", summary="List policies")
async def list_policies(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                        _: User = Depends(require_roles(Role.ADMIN, Role.ENGINEER)),
                        session: AsyncSession = Depends(get_db_session)) -> dict:
    policies = list((await session.scalars(select(Policy).order_by(Policy.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))).all())
    count = await session.scalar(select(func.count()).select_from(Policy)) or 0
    return {"data": [_read(item) for item in policies], "pagination": {"page": page, "page_size": page_size,
            "total": count, "total_pages": (count + page_size - 1) // page_size if count else 0}}


@router.post("", status_code=201, summary="Create policy")
async def create_policy(payload: PolicyCreate, current_user: User = Depends(require_roles(Role.ADMIN)),
                        session: AsyncSession = Depends(get_db_session)) -> dict:
    _validate_policy(payload)
    policy = Policy(**payload.model_dump(), created_by=current_user.id)
    session.add(policy)
    await session.commit()
    await session.refresh(policy)
    return {"data": _read(policy)}


@router.patch("/{policy_id}", summary="Update policy")
async def update_policy(policy_id: uuid.UUID, payload: PolicyPatch, current_user: User = Depends(require_roles(Role.ADMIN)),
                        session: AsyncSession = Depends(get_db_session)) -> dict:
    policy = await session.get(Policy, policy_id)
    if policy is None:
        raise AppError("POLICY_NOT_FOUND", "Policy does not exist", 404)
    _validate_policy(payload, policy)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(policy, key, value)
    await session.commit()
    await session.refresh(policy)
    return {"data": _read(policy)}
