from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.domain import Incident, IncidentStatus, Severity
from app.repositories.pagination import PageResult, pagination_window


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, incident_id: uuid.UUID) -> Incident | None:
        return await self.session.scalar(select(Incident).where(Incident.id == incident_id))

    async def get_by_number(self, incident_number: str) -> Incident | None:
        return await self.session.scalar(select(Incident).where(Incident.incident_number == incident_number))

    async def create(self, incident: Incident) -> Incident:
        self.session.add(incident)
        await self.session.flush()
        return incident

    async def list(
        self,
        *,
        status: IncidentStatus | None = None,
        severity: Severity | None = None,
        service_id: uuid.UUID | None = None,
        assigned_to: uuid.UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PageResult[Incident]:
        offset, limit = pagination_window(page, page_size)
        filters = []
        if status is not None:
            filters.append(Incident.status == status)
        if severity is not None:
            filters.append(Incident.severity == severity)
        if service_id is not None:
            filters.append(Incident.service_id == service_id)
        if assigned_to is not None:
            filters.append(Incident.assigned_to == assigned_to)
        if created_from is not None:
            filters.append(Incident.created_at >= created_from)
        if created_to is not None:
            filters.append(Incident.created_at <= created_to)
        total = await self.session.scalar(select(func.count()).select_from(Incident).where(*filters)) or 0
        items = list((await self.session.scalars(
            select(Incident).where(*filters).order_by(Incident.created_at.desc()).offset(offset).limit(limit)
        )).all())
        return PageResult(items, page, page_size, total)

    async def get_active_for_service(self, service_id: uuid.UUID, statuses: set[IncidentStatus]) -> list[Incident]:
        result = await self.session.scalars(
            select(Incident).where(Incident.service_id == service_id, Incident.status.in_(statuses))
            .options(selectinload(Incident.alerts))
            .order_by(Incident.created_at.desc()).with_for_update()
        )
        return list(result.all())
