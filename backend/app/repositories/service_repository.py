import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Service
from app.repositories.pagination import PageResult, pagination_window


class ServiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, service_id: uuid.UUID) -> Service | None:
        return await self.session.scalar(select(Service).where(Service.id == service_id))

    async def get_by_name(self, name: str) -> Service | None:
        return await self.session.scalar(select(Service).where(Service.name == name))

    async def create(self, service: Service) -> Service:
        self.session.add(service)
        await self.session.flush()
        return service

    async def list(self, *, page: int = 1, page_size: int = 50) -> PageResult[Service]:
        offset, limit = pagination_window(page, page_size)
        total = await self.session.scalar(select(func.count()).select_from(Service)) or 0
        items = list((await self.session.scalars(select(Service).order_by(Service.name).offset(offset).limit(limit))).all())
        return PageResult(items, page, page_size, total)
