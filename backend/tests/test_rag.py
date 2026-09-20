import uuid

import pytest

from app.core.config import Settings
from app.rag.chunking import KnowledgeSource, chunk_document, clean_document
from app.rag.embeddings import MockEmbeddingProvider
from app.rag.service import RAGService


class FakeQdrant:
    def __init__(self):
        self.points = []
        self.filters = []

    async def delete_document(self, document_id):
        self.points = [point for point in self.points if point["payload"]["document_id"] != document_id]

    async def upsert(self, points):
        self.points.extend(points)

    async def search(self, vector, *, limit, filters=None):
        self.filters.append(filters)
        return [{"score": 0.75, "payload": point["payload"]} for point in self.points[:limit]]


def test_chunking_is_clean_bounded_and_deterministic():
    source = KnowledgeSource(str(uuid.uuid4()), "RUNBOOK", "DB", "# Troubleshooting\n\npassword=secret\n" + "x" * 500)
    first = chunk_document(source, chunk_size=100, overlap=20)
    second = chunk_document(source, chunk_size=100, overlap=20)
    assert first == second
    assert first
    assert all(len(chunk.content) <= 100 for chunk in first)
    assert "[REDACTED]" in clean_document("password=secret")


@pytest.mark.asyncio
async def test_mock_embeddings_are_deterministic_and_dimension_consistent():
    provider = MockEmbeddingProvider(dimension=16)
    first = await provider.embed_text("database connection exhaustion")
    second = await provider.embed_text("database connection exhaustion")
    other = await provider.embed_text("high cpu")
    assert first == second
    assert first != other
    assert len(first) == 16


@pytest.mark.asyncio
async def test_rag_retrieval_bounds_results_and_preserves_citations():
    settings = Settings(embedding_dimension=16, rag_max_results=2)
    qdrant = FakeQdrant()
    service = RAGService(None, settings=settings, embeddings=MockEmbeddingProvider(dimension=16), qdrant=qdrant)
    source = KnowledgeSource("doc-1", "RUNBOOK", "Database", "database connection exhaustion", service_id="svc-1")
    chunks = chunk_document(source, chunk_size=200, overlap=20)
    vectors = await service.embeddings.embed_documents([chunk.content for chunk in chunks])
    await qdrant.upsert([{"id": chunk.chunk_id, "vector": vector, "payload": {
        "document_id": source.document_id, "document_type": source.document_type, "title": source.title,
        "chunk_id": chunk.chunk_id, "content": chunk.content, "service_id": source.service_id,
    }} for chunk, vector in zip(chunks, vectors)])
    results = await service.retrieve("database connection exhaustion", service_id=uuid.UUID("00000000-0000-0000-0000-000000000001"), top_k=20)
    assert len(results) <= 2
    assert results[0]["document_id"] == "doc-1"
    assert "chunk_id" in results[0]
