"""Optional Qdrant-backed episodic memory adapter."""
from __future__ import annotations
from typing import Any, Mapping, Sequence
from omega.memory.store import MemoryRecord, VectorStore

class QdrantVectorStore:
    def __init__(self, *, url: str, collection: str, dimensions: int = 256, api_key: str | None = None) -> None:
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.http import models
        except ImportError as exc: raise RuntimeError("Install omega-agent-os[qdrant] to use QdrantVectorStore") from exc
        self._models = models; self._client = AsyncQdrantClient(url=url, api_key=api_key); self.collection = collection; self.dimensions = dimensions
    async def ensure_collection(self) -> None:
        from qdrant_client.http import models
        collections = await self._client.get_collections()
        if self.collection not in {c.name for c in collections.collections}:
            await self._client.create_collection(self.collection, vectors_config=models.VectorParams(size=self.dimensions, distance=models.Distance.COSINE))
    async def upsert(self, record: MemoryRecord, vector: Sequence[float]) -> None:
        await self.ensure_collection(); await self._client.upsert(self.collection, points=[self._models.PointStruct(id=record.id, vector=list(vector), payload={"text":record.text,"metadata":dict(record.metadata),"created_at":record.created_at})])
    async def search(self, vector: Sequence[float], *, limit: int = 5) -> Sequence[tuple[MemoryRecord, float]]:
        await self.ensure_collection(); hits = await self._client.search(self.collection, query_vector=list(vector), limit=limit)
        return tuple((MemoryRecord(str(h.id), str(h.payload.get("text","")), h.payload.get("metadata",{}), float(h.payload.get("created_at",0))), float(h.score)) for h in hits)
