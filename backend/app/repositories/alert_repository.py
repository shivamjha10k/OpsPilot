import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Alert, Severity
from app.repositories.pagination import PageResult, pagination_window


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, alert: Alert) -> Alert:
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def list_by_service(
        self, service_id: uuid.UUID, *, severity: Severity | None = None, page: int = 1, page_size: int = 50
    ) -> PageResult[Alert]:
        offset, limit = pagination_window(page, page_size)
        filters = [Alert.service_id == service_id]
        if severity is not None:
            filters.append(Alert.severity == severity)
        total = await self.session.scalar(select(func.count()).select_from(Alert).where(*filters)) or 0
        items = list((await self.session.scalars(
            select(Alert).where(*filters).order_by(Alert.occurred_at.desc()).offset(offset).limit(limit)
        )).all())
        return PageResult(items, page, page_size, total)

    async def get_by_event_id(self, event_id: str) -> Alert | None:
        return await self.session.scalar(
            select(Alert).where(Alert.payload["event_id"].as_string() == event_id)
        )

    async def list(
        self, *, service_id: uuid.UUID | None = None, severity: Severity | None = None,
        alert_type: str | None = None, occurred_from: datetime | None = None,
        occurred_to: datetime | None = None, page: int = 1, page_size: int = 50
    ) -> PageResult[Alert]:
        offset, limit = pagination_window(page, page_size)
        filters = []
        if service_id is not None:
            filters.append(Alert.service_id == service_id)
        if severity is not None:
            filters.append(Alert.severity == severity)
        if alert_type is not None:
            filters.append(Alert.alert_type == alert_type)
        if occurred_from is not None:
            filters.append(Alert.occurred_at >= occurred_from)
        if occurred_to is not None:
            filters.append(Alert.occurred_at <= occurred_to)
        total = await self.session.scalar(select(func.count()).select_from(Alert).where(*filters)) or 0
        items = list((await self.session.scalars(
            select(Alert).where(*filters).order_by(Alert.occurred_at.desc()).offset(offset).limit(limit)
        )).all())
        return PageResult(items, page, page_size, total)
