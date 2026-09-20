from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.core.config import Settings


class EmbeddingProviderError(Exception):
    """Normalized embedding provider failure."""


class EmbeddingProvider(Protocol):
    model: str
    dimension: int

    async def embed_text(self, text: str) -> list[float]: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class MockEmbeddingProvider:
    """Offline deterministic embeddings for development and test environments."""

    def __init__(self, settings: Settings | None = None, *, dimension: int | None = None) -> None:
        self.model = settings.embedding_model if settings else "mock-embedding-v1"
        self.dimension = dimension or (settings.embedding_dimension if settings else 64)
        if self.dimension < 8:
            raise ValueError("embedding dimension must be at least 8")

    async def embed_text(self, text: str) -> list[float]:
        if not isinstance(text, str) or not text.strip() or len(text) > 100_000:
            raise ValueError("embedding input must be a non-empty bounded string")
        values = []
        for index in range(self.dimension):
            digest = hashlib.sha256(f"{self.model}:{index}:{text}".encode("utf-8")).digest()
            values.append((int.from_bytes(digest[:4], "big") / 2**31) - 1)
        norm = math.sqrt(sum(value * value for value in values)) or 1
        return [value / norm for value in values]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if len(texts) > 128:
            raise ValueError("embedding batch is too large")
        return [await self.embed_text(text) for text in texts]


def embedding_provider_from_settings(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider.lower() == "mock":
        return MockEmbeddingProvider(settings)
    raise EmbeddingProviderError("configured embedding provider is unavailable")
