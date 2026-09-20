from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_resource(self, resource_type: str, resource_id: str) -> list[AuditLog]:
        result = await self.session.scalars(
            select(AuditLog)
            .where(AuditLog.resource_type == resource_type, AuditLog.resource_id == resource_id)
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        )
        return list(result.all())
