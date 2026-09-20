import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_roles
from app.core.database import get_db_session
from app.core.errors import AppError
from app.models.domain import Event
from app.models.user import Role, User
from app.repositories.event_repository import EventRepository
from app.schemas.domain import EventCreate, EventRead, Page, Pagination
from app.services.incident_engine import IncidentEngine
from app.workers.tasks.event_tasks import process_event_task

router = APIRouter(prefix="/events", tags=["events"])


def _timestamp(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise AppError("INVALID_EVENT", "timestamps must include timezone information", 422)
    return value


@router.post("", status_code=status.HTTP_201_CREATED, summary="Ingest an operational event")
async def ingest_event(
    payload: EventCreate,
    request: Request,
    current_user: User = Depends(require_roles(Role.ENGINEER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    event = Event(
        event_id=payload.event_id.strip(), event_type=payload.event_type.strip(), source=payload.source.strip(),
        service_id=payload.service_id, payload=payload.payload, occurred_at=payload.occurred_at,
    )
    request_id = request.headers.get("X-Request-ID")
    engine = IncidentEngine(session)
    persisted, duplicate = await engine.persist_event(event, request_id=request_id)
    if duplicate:
        return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder({"data": {
            "event_id": persisted.event_id, "status": persisted.processing_status.value,
            "task_id": persisted.task_id, "duplicate": True,
        }}))
    await engine.mark_queued(persisted.event_id)
    try:
        queued = process_event_task.apply_async(args=[persisted.event_id], kwargs={"request_id": request_id})
        await engine.set_task_id(persisted.event_id, queued.id)
    except Exception as exc:
        await engine.mark_queue_failed(persisted.event_id, f"queue unavailable: {exc}")
        raise AppError("EVENT_QUEUE_UNAVAILABLE", "Event was persisted but could not be queued", 503) from exc
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=jsonable_encoder({"data": {
        "event_id": persisted.event_id, "status": "QUEUED", "task_id": queued.id,
    }}))


@router.get("", response_model=None, summary="List operational events")
async def list_events(
    service_id: uuid.UUID | None = None,
    event_type: str | None = None,
    source: str | None = None,
    processed: bool | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await EventRepository(session).list(
        service_id=service_id, event_type=event_type, source=source, processed=processed,
        occurred_from=_timestamp(occurred_from), occurred_to=_timestamp(occurred_to),
        page=page, page_size=page_size,
    )
    return {"data": [EventRead.model_validate(item).model_dump(mode="json") for item in result.items],
            "pagination": Pagination(page=result.page, page_size=result.page_size, total=result.total,
                                      total_pages=result.total_pages).model_dump()}
