import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Runbook
from app.repositories.pagination import PageResult, pagination_window


class RunbookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, runbook_id: uuid.UUID) -> Runbook | None:
        return await self.session.scalar(select(Runbook).where(Runbook.id == runbook_id))

    async def create(self, runbook: Runbook) -> Runbook:
        self.session.add(runbook)
        await self.session.flush()
        return runbook

    async def list(
        self, *, query: str | None = None, page: int = 1, page_size: int = 50
    ) -> PageResult[Runbook]:
        offset, limit = pagination_window(page, page_size)
        filters = []
        if query:
            pattern = f"%{query}%"
            filters.append(Runbook.title.ilike(pattern) | Runbook.description.ilike(pattern))
        total = await self.session.scalar(select(func.count()).select_from(Runbook).where(*filters)) or 0
        items = list((await self.session.scalars(
            select(Runbook).where(*filters).order_by(Runbook.title).offset(offset).limit(limit)
        )).all())
        return PageResult(items, page, page_size, total)
