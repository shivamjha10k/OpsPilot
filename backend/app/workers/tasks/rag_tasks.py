from __future__ import annotations

import uuid

from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import get_settings
from app.core.async_runner import run_in_worker_loop
from app.core.database import SessionLocal
from app.rag.service import RAGService
from app.workers.celery_app import celery_app


async def _index(kind: str, document_id: str) -> int:
    async with SessionLocal() as session:
        service = RAGService(session)
        if kind == "runbook":
            return await service.index_runbook(uuid.UUID(document_id))
        if kind == "incident":
            return await service.index_incident(uuid.UUID(document_id))
        return await service.index_knowledge_document(uuid.UUID(document_id))


@celery_app.task(bind=True, name="opspilot.index_runbook", max_retries=3)
def index_runbook_task(self, document_id: str) -> dict:
    return _run_index(self, "runbook", document_id)


@celery_app.task(bind=True, name="opspilot.index_incident", max_retries=3)
def index_incident_task(self, document_id: str) -> dict:
    return _run_index(self, "incident", document_id)


@celery_app.task(bind=True, name="opspilot.reindex_document", max_retries=3)
def reindex_document_task(self, document_id: str) -> dict:
    return _run_index(self, "document", document_id)


def _run_index(task, kind: str, document_id: str) -> dict:
    try:
        uuid.UUID(document_id)
        count = run_in_worker_loop(_index(kind, document_id))
        return {"document_id": document_id, "status": "INDEXED", "chunk_count": count}
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid knowledge document identifier") from exc
    except SoftTimeLimitExceeded:
        raise
    except Exception as exc:
        if task.request.retries < get_settings().ai_max_retries:
            raise task.retry(exc=exc, countdown=min(60, 2 ** task.request.retries))
        return {"document_id": document_id, "status": "FAILED", "error": type(exc).__name__}


@celery_app.task(bind=True, name="opspilot.rebuild_knowledge_index", max_retries=1)
def rebuild_knowledge_index_task(self) -> dict:
    try:
        async def run():
            async with SessionLocal() as session:
                return await RAGService(session).rebuild_knowledge_index()
        return {"status": "INDEXED", "chunk_count": run_in_worker_loop(run())}
    except Exception as exc:
        if self.request.retries < 1:
            raise self.retry(exc=exc, countdown=5)
        return {"status": "FAILED", "error": type(exc).__name__}
