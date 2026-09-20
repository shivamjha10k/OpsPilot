from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.core.database import get_db_session
from app.core.errors import AppError
from app.models.domain import AuditLog
from app.models.user import Role, User
from app.workers.tasks.rag_tasks import index_runbook_task

router = APIRouter(prefix="/runbooks", tags=["knowledge"])


@router.post("/{runbook_id}/index", status_code=202, summary="Queue runbook indexing")
async def index_runbook(
    runbook_id: uuid.UUID,
    current_user: User = Depends(require_roles(Role.ADMIN, Role.ENGINEER)),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        task = index_runbook_task.apply_async(args=[str(runbook_id)])
    except Exception as exc:
        raise AppError("KNOWLEDGE_QUEUE_UNAVAILABLE", "Knowledge indexing could not be queued", 503) from exc
    session.add(AuditLog(actor_id=current_user.id, action="KNOWLEDGE_INDEX_REQUESTED", resource_type="Runbook",
                         resource_id=str(runbook_id), result="SUCCESS", metadata_json={"task_id": task.id}))
    await session.commit()
    return {"data": {"document_id": str(runbook_id), "status": "QUEUED", "task_id": task.id}}
