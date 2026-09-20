from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.models.domain import (
    AIInvestigation, Incident, IncidentStatus, KnowledgeDocument, KnowledgeDocumentStatus,
    KnowledgeIndexStatus, KnowledgeDocumentType, Runbook, RunbookStatus,
)
from app.rag.chunking import KnowledgeSource, chunk_document
from app.rag.embeddings import EmbeddingProvider, embedding_provider_from_settings
from app.rag.qdrant_repository import QdrantRepository


class RAGService:
    def __init__(self, session: AsyncSession, *, settings: Settings | None = None,
                 embeddings: EmbeddingProvider | None = None, qdrant: QdrantRepository | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.embeddings = embeddings or embedding_provider_from_settings(self.settings)
        self.qdrant = qdrant or QdrantRepository(self.settings)

    async def index_runbook(self, document_id: uuid.UUID) -> int:
        source = await self.session.scalar(select(Runbook).where(Runbook.id == document_id))
        if source is None:
            raise ValueError("runbook does not exist")
        if source.status is not RunbookStatus.ACTIVE:
            raise ValueError("only active runbooks are indexable")
        knowledge = KnowledgeSource(str(source.id), KnowledgeDocumentType.RUNBOOK.value, source.title,
                                    f"# {source.title}\n\n{source.description}\n\n{source.content}", version=str(source.version),
                                    created_at=str(source.created_at), updated_at=str(source.updated_at))
        return await self._index_source(knowledge)

    async def index_incident(self, incident_id: uuid.UUID) -> int:
        incident = await self.session.scalar(select(Incident).where(Incident.id == incident_id).options(selectinload(Incident.alerts)))
        if incident is None:
            raise ValueError("incident does not exist")
        if incident.status not in {IncidentStatus.RESOLVED, IncidentStatus.ESCALATED, IncidentStatus.DIAGNOSED}:
            raise ValueError("only sufficiently complete incidents are indexable")
        investigation = await self.session.scalar(select(AIInvestigation).where(AIInvestigation.incident_id == incident.id,
                                                                                AIInvestigation.status == "COMPLETED")
                                                   .order_by(AIInvestigation.created_at.desc()))
        alert_text = "\n".join(f"Alert: {alert.message}" for alert in incident.alerts)
        investigation_text = f"\nInvestigation: {investigation.summary}\nRoot cause: {investigation.root_cause}" if investigation else ""
        content = f"# {incident.title}\n\n{incident.description}\n\nService: {incident.service_id}\nSeverity: {incident.severity.value}\n{alert_text}{investigation_text}"
        knowledge = KnowledgeSource(str(incident.id), KnowledgeDocumentType.HISTORICAL_INCIDENT.value, incident.title, content,
                                    service_id=str(incident.service_id), created_at=str(incident.created_at), updated_at=str(incident.updated_at))
        return await self._index_source(knowledge)

    async def index_knowledge_document(self, document_id: uuid.UUID) -> int:
        source = await self.session.get(KnowledgeDocument, document_id)
        if source is None:
            raise ValueError("knowledge document does not exist")
        if source.status is not KnowledgeDocumentStatus.ACTIVE:
            raise ValueError("only active knowledge documents are indexable")
        source.index_status = KnowledgeIndexStatus.INDEXING
        source.index_error = None
        await self.session.commit()
        knowledge = KnowledgeSource(str(source.id), source.document_type.value, source.title, source.content,
                                    service_id=str(source.service_id) if source.service_id else None,
                                    environment=source.environment.value if source.environment else None,
                                    version=source.version, created_at=str(source.created_at), updated_at=str(source.updated_at))
        try:
            count = await self._index_source(knowledge)
            source.index_status = KnowledgeIndexStatus.INDEXED
            await self.session.commit()
            return count
        except Exception as exc:
            source.index_status = KnowledgeIndexStatus.FAILED
            source.index_error = type(exc).__name__[:500]
            await self.session.commit()
            raise

    async def _index_source(self, source: KnowledgeSource) -> int:
        chunks = chunk_document(source, chunk_size=self.settings.rag_chunk_size, overlap=self.settings.rag_chunk_overlap)
        if not chunks:
            raise ValueError("document produced no chunks")
        vectors = await self.embeddings.embed_documents([chunk.content for chunk in chunks])
        if any(len(vector) != self.settings.embedding_dimension for vector in vectors):
            raise ValueError("embedding dimension does not match configuration")
        await self.qdrant.delete_document(source.document_id)
        points = []
        for chunk, vector in zip(chunks, vectors):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"opspilot:{source.document_id}:{chunk.chunk_id}"))
            payload = {"document_id": source.document_id, "document_type": source.document_type, "title": source.title,
                       "chunk_id": chunk.chunk_id, "content": chunk.content, "section": chunk.section,
                       "source": source.source, "embedding_model": self.embeddings.model,
                       "embedding_dimension": self.embeddings.dimension}
            for key in ("service_id", "environment", "version", "created_at", "updated_at"):
                value = getattr(source, key)
                if value is not None:
                    payload[key] = value
            points.append({"id": point_id, "vector": vector, "payload": payload})
        await self.qdrant.upsert(points)
        return len(points)

    async def retrieve(self, query: str, *, service_id: uuid.UUID | None = None, environment: str | None = None,
                       document_types: list[str] | None = None, top_k: int | None = None) -> list[dict[str, Any]]:
        if not query or len(query) > 2000:
            raise ValueError("retrieval query must be non-empty and bounded")
        limit = min(top_k or self.settings.rag_top_k, self.settings.rag_max_results)
        if limit < 1:
            raise ValueError("top_k must be positive")
        vector = await self.embeddings.embed_text(query)
        base = {}
        if service_id:
            base["service_id"] = str(service_id)
        if environment:
            base["environment"] = environment
        if document_types:
            base["document_type"] = document_types[:10]
        filters = [base]
        if environment and base:
            filters.append({key: value for key, value in base.items() if key != "environment"})
        if service_id:
            filters.append({key: value for key, value in base.items() if key not in {"service_id", "environment"}})
        filters.append({key: value for key, value in base.items() if key == "document_type"})
        filters.append({})
        for current in filters:
            raw = await self.qdrant.search(vector, limit=limit, filters=current or None)
            results = self._validate_results(raw)[:limit]
            if results:
                return results
        return []

    async def rebuild_knowledge_index(self) -> int:
        await self.qdrant.recreate_collection()
        total = 0
        runbooks = (await self.session.scalars(select(Runbook).where(Runbook.status == RunbookStatus.ACTIVE))).all()
        for runbook in runbooks:
            total += await self.index_runbook(runbook.id)
        incidents = (await self.session.scalars(select(Incident).where(Incident.status.in_({IncidentStatus.RESOLVED, IncidentStatus.ESCALATED, IncidentStatus.DIAGNOSED})))).all()
        for incident in incidents:
            total += await self.index_incident(incident.id)
        documents = (await self.session.scalars(select(KnowledgeDocument).where(KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE))).all()
        for document in documents:
            total += await self.index_knowledge_document(document.id)
        return total

    def _validate_results(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        valid = []
        for item in raw[: self.settings.rag_max_results]:
            payload = item.get("payload") if isinstance(item, dict) else None
            score = item.get("score") if isinstance(item, dict) else None
            if not isinstance(payload, dict) or not isinstance(score, (int, float)):
                continue
            required = {"document_id", "document_type", "title", "chunk_id", "content"}
            if not required.issubset(payload) or not isinstance(payload["content"], str):
                continue
            payload = dict(payload)
            payload["content"] = payload["content"][: self.settings.rag_max_context_chars]
            valid.append({"document_id": str(payload["document_id"]), "document_type": str(payload["document_type"]),
                          "title": str(payload["title"]), "chunk_id": str(payload["chunk_id"]), "score": float(score),
                          "content": payload["content"], "metadata": payload})
        return valid
