import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_roles
from app.core.database import get_db_session
from app.core.errors import AppError
from app.models.domain import Incident, IncidentStatus, Severity
from app.models.user import Role, User
from app.repositories.audit_repository import AuditRepository
from app.repositories.incident_repository import IncidentRepository
from app.schemas.domain import (
    IncidentAssignRequest, IncidentRead, IncidentPageFilters, ManualIncidentCreate, Pagination, TimelineEntry,
)
from app.services.incident_engine import IncidentEngine

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise AppError("INVALID_INCIDENT", "timestamps must include timezone information", 422)
    return value


def _read(incident: Incident) -> dict:
    return IncidentRead.model_validate(incident).model_dump(mode="json")


@router.get("", summary="List incidents")
async def list_incidents(
    status: IncidentStatus | None = None,
    severity: Severity | None = None,
    service_id: uuid.UUID | None = None,
    assigned_to: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await IncidentRepository(session).list(
        status=status, severity=severity, service_id=service_id, assigned_to=assigned_to,
        created_from=_aware(created_from), created_to=_aware(created_to), page=page, page_size=page_size,
    )
    return {"data": [_read(item) for item in result.items],
            "pagination": Pagination(page=result.page, page_size=result.page_size, total=result.total,
                                      total_pages=result.total_pages).model_dump()}


@router.get("/{incident_id}", summary="Get an incident")
async def get_incident(incident_id: uuid.UUID, _: User = Depends(get_current_user),
                       session: AsyncSession = Depends(get_db_session)) -> dict:
    incident = await IncidentRepository(session).get_by_id(incident_id)
    if incident is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident does not exist", 404)
    return {"data": _read(incident)}


@router.post("", status_code=201, summary="Create a manual incident")
async def create_incident(
    payload: ManualIncidentCreate,
    current_user: User = Depends(require_roles(Role.ENGINEER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    incident = await IncidentEngine(session).create_manual(
        title=payload.title.strip(), description=payload.description.strip(), service_id=payload.service_id,
        severity=payload.severity, detected_at=payload.detected_at, actor=current_user,
    )
    return {"data": _read(incident)}


@router.post("/{incident_id}/acknowledge", summary="Acknowledge an incident")
async def acknowledge_incident(incident_id: uuid.UUID,
                               current_user: User = Depends(require_roles(Role.ENGINEER, Role.ADMIN)),
                               session: AsyncSession = Depends(get_db_session)) -> dict:
    incident = await IncidentEngine(session).acknowledge(incident_id, current_user)
    return {"data": _read(incident)}


@router.post("/{incident_id}/assign", summary="Assign an incident")
async def assign_incident(incident_id: uuid.UUID, payload: IncidentAssignRequest,
                          current_user: User = Depends(require_roles(Role.ENGINEER, Role.ADMIN)),
                          session: AsyncSession = Depends(get_db_session)) -> dict:
    incident = await IncidentEngine(session).assign(incident_id, payload.user_id, current_user)
    return {"data": _read(incident)}


@router.post("/{incident_id}/escalate", summary="Escalate an incident")
async def escalate_incident(incident_id: uuid.UUID,
                            current_user: User = Depends(require_roles(Role.ENGINEER, Role.ADMIN)),
                            session: AsyncSession = Depends(get_db_session)) -> dict:
    incident = await IncidentEngine(session).escalate(incident_id, current_user)
    return {"data": _read(incident)}


@router.get("/{incident_id}/timeline", summary="Get incident timeline")
async def incident_timeline(incident_id: uuid.UUID, _: User = Depends(get_current_user),
                            session: AsyncSession = Depends(get_db_session)) -> dict:
    if await IncidentRepository(session).get_by_id(incident_id) is None:
        raise AppError("INCIDENT_NOT_FOUND", "Incident does not exist", 404)
    entries = await AuditRepository(session).list_for_resource("Incident", str(incident_id))
    timeline = [TimelineEntry(
        id=item.id, action=item.action, resource_type=item.resource_type, resource_id=item.resource_id,
        actor_id=item.actor_id, result=item.result, metadata=item.metadata_json or {}, created_at=item.created_at,
    ).model_dump(mode="json") for item in entries]
    return {"data": timeline}
