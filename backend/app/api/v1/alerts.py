import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db_session
from app.core.errors import AppError
from app.models.domain import Severity
from app.models.user import User
from app.repositories.alert_repository import AlertRepository
from app.schemas.domain import AlertPageFilters, AlertRead, Pagination

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise AppError("INVALID_ALERT", "timestamps must include timezone information", 422)
    return value


@router.get("", summary="List alerts")
async def list_alerts(
    service_id: uuid.UUID | None = None,
    severity: Severity | None = None,
    alert_type: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await AlertRepository(session).list(
        service_id=service_id, severity=severity, alert_type=alert_type,
        occurred_from=_aware(occurred_from), occurred_to=_aware(occurred_to),
        page=page, page_size=page_size,
    )
    return {"data": [AlertRead.model_validate(item).model_dump(mode="json") for item in result.items],
            "pagination": Pagination(page=result.page, page_size=result.page_size, total=result.total,
                                      total_pages=result.total_pages).model_dump()}
