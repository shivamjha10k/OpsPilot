import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Event
from app.repositories.pagination import PageResult, pagination_window


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_event_id(self, event_id: str) -> Event | None:
        return await self.session.scalar(select(Event).where(Event.event_id == event_id))

    async def create(self, event: Event) -> Event:
        self.session.add(event)
        await self.session.flush()
        return event

    async def list(
        self, *, service_id: uuid.UUID | None = None, event_type: str | None = None,
        source: str | None = None, processed: bool | None = None,
        occurred_from: datetime | None = None, occurred_to: datetime | None = None,
        page: int = 1, page_size: int = 50
    ) -> PageResult[Event]:
        offset, limit = pagination_window(page, page_size)
        filters = []
        if service_id is not None:
            filters.append(Event.service_id == service_id)
        if event_type is not None:
            filters.append(Event.event_type == event_type)
        if source is not None:
            filters.append(Event.source == source)
        if processed is not None:
            filters.append(Event.processed == processed)
        if occurred_from is not None:
            filters.append(Event.occurred_at >= occurred_from)
        if occurred_to is not None:
            filters.append(Event.occurred_at <= occurred_to)
        total = await self.session.scalar(select(func.count()).select_from(Event).where(*filters)) or 0
        items = list((await self.session.scalars(
            select(Event).where(*filters).order_by(Event.occurred_at.desc()).offset(offset).limit(limit)
        )).all())
        return PageResult(items, page, page_size, total)

    async def list_by_service(
        self, service_id: uuid.UUID, *, page: int = 1, page_size: int = 50
    ) -> PageResult[Event]:
        return await self.list(service_id=service_id, page=page, page_size=page_size)
