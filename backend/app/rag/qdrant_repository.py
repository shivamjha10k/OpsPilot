from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings


class QdrantUnavailable(RuntimeError):
    """Qdrant could not be reached or returned an invalid response."""


class QdrantRepository:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.qdrant_url.rstrip("/")
        self.collection = settings.qdrant_collection_name
        self.dimension = settings.embedding_dimension
        self.headers = {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else {}
        self.timeout = settings.embedding_timeout_seconds

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/healthz", headers=self.headers)
            return response.is_success
        except httpx.HTTPError:
            return False

    async def ensure_collection(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/collections/{self.collection}", headers=self.headers)
                if response.status_code == 404:
                    response = await client.put(
                        f"{self.base_url}/collections/{self.collection}", headers=self.headers,
                        json={"vectors": {"size": self.dimension, "distance": "Cosine"}},
                    )
                if not response.is_success:
                    raise QdrantUnavailable(f"collection operation returned {response.status_code}")
                if response.request.method == "GET":
                    size = response.json().get("result", {}).get("config", {}).get("params", {}).get("vectors", {}).get("size")
                    if size is not None and int(size) != self.dimension:
                        raise QdrantUnavailable("qdrant collection dimension does not match embedding provider")
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise QdrantUnavailable("qdrant collection is unavailable") from exc

    async def upsert(self, points: list[dict[str, Any]]) -> None:
        await self.ensure_collection()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.put(
                    f"{self.base_url}/collections/{self.collection}/points?wait=true", headers=self.headers,
                    json={"points": points},
                )
            if not response.is_success:
                raise QdrantUnavailable("qdrant upsert failed")
        except httpx.HTTPError as exc:
            raise QdrantUnavailable("qdrant upsert failed") from exc

    async def delete_document(self, document_id: str) -> None:
        await self.ensure_collection()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/collections/{self.collection}/points/delete?wait=true", headers=self.headers,
                    json={"filter": {"must": [{"key": "document_id", "match": {"value": document_id}}]}},
                )
            if not response.is_success:
                raise QdrantUnavailable("qdrant delete failed")
        except httpx.HTTPError as exc:
            raise QdrantUnavailable("qdrant delete failed") from exc

    async def recreate_collection(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                await client.delete(f"{self.base_url}/collections/{self.collection}", headers=self.headers)
            await self.ensure_collection()
        except httpx.HTTPError as exc:
            raise QdrantUnavailable("qdrant collection rebuild failed") from exc

    async def search(self, vector: list[float], *, limit: int, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        await self.ensure_collection()
        body: dict[str, Any] = {"vector": vector, "limit": limit, "with_payload": True}
        if filters:
            must = []
            for key, value in filters.items():
                if isinstance(value, list):
                    must.append({"key": key, "match": {"any": value}})
                else:
                    must.append({"key": key, "match": {"value": value}})
            body["filter"] = {"must": must}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/collections/{self.collection}/points/search", headers=self.headers, json=body)
            if not response.is_success:
                raise QdrantUnavailable("qdrant search failed")
            return response.json().get("result", [])
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise QdrantUnavailable("qdrant search failed") from exc
