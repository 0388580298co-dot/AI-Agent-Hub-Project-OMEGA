"""Async short-term and long-term memory abstractions with an in-memory vector store."""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: str
    text: str
    metadata: Mapping[str, Any]
    created_at: float


class MemoryStore(Protocol):
    async def remember(self, text: str, *, metadata: Mapping[str, Any] | None = None) -> None: ...
    async def recall(self, query: str, *, limit: int = 5) -> Sequence[MemoryRecord]: ...


class VectorStore(Protocol):
    async def upsert(self, record: MemoryRecord, vector: Sequence[float]) -> None: ...
    async def search(self, vector: Sequence[float], *, limit: int = 5) -> Sequence[tuple[MemoryRecord, float]]: ...


class InMemoryVectorStore:
    """Thread-safe async vector store suitable for development and deterministic tests."""

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions < 16:
            raise ValueError("dimensions must be >= 16")
        self.dimensions = dimensions
        self._items: dict[str, tuple[MemoryRecord, tuple[float, ...]]] = {}
        self._lock = asyncio.Lock()

    async def upsert(self, record: MemoryRecord, vector: Sequence[float]) -> None:
        normalized = tuple(float(value) for value in vector)
        if len(normalized) != self.dimensions:
            raise ValueError("Vector dimension mismatch")
        async with self._lock:
            self._items[record.id] = (record, normalized)

    async def search(self, vector: Sequence[float], *, limit: int = 5) -> Sequence[tuple[MemoryRecord, float]]:
        if limit < 1:
            return ()
        query = tuple(float(value) for value in vector)
        if len(query) != self.dimensions:
            raise ValueError("Vector dimension mismatch")
        async with self._lock:
            items = list(self._items.values())
        scored = [(record, self._cosine(query, stored)) for record, stored in items]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return tuple(scored[:limit])

    @staticmethod
    def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)


class HashEmbedding:
    """Deterministic local embedding used to keep the reference runtime dependency-light."""

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions < 16:
            raise ValueError("dimensions must be >= 16")
        self.dimensions = dimensions

    async def embed(self, text: str) -> tuple[float, ...]:
        tokens = re.findall(r"[\w-]+", text.lower())
        vector = [0.0] * self.dimensions
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return tuple(vector)


class InMemoryMemoryStore:
    """Unified short/long-term memory facade backed by a vector index."""

    def __init__(self, *, dimensions: int = 256, short_term_limit: int = 32) -> None:
        if short_term_limit < 1:
            raise ValueError("short_term_limit must be >= 1")
        self._embedding = HashEmbedding(dimensions)
        self._vectors = InMemoryVectorStore(dimensions)
        self._short_term: list[MemoryRecord] = []
        self._lock = asyncio.Lock()
        self._short_term_limit = short_term_limit

    async def remember(self, text: str, *, metadata: Mapping[str, Any] | None = None) -> None:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Memory text cannot be empty")
        record = MemoryRecord(id=str(uuid.uuid4()), text=text.strip(), metadata=dict(metadata or {}), created_at=time.time())
        vector = await self._embedding.embed(record.text)
        await self._vectors.upsert(record, vector)
        async with self._lock:
            self._short_term.append(record)
            if len(self._short_term) > self._short_term_limit:
                del self._short_term[:-self._short_term_limit]

    async def recall(self, query: str, *, limit: int = 5) -> Sequence[MemoryRecord]:
        if not query.strip():
            return ()
        if limit < 1:
            return ()
        vector = await self._embedding.embed(query)
        matches = await self._vectors.search(vector, limit=limit)
        return tuple(record for record, score in matches if score > 0)

    async def recent(self, *, limit: int = 10) -> Sequence[MemoryRecord]:
        if limit < 1:
            return ()
        async with self._lock:
            return tuple(self._short_term[-limit:][::-1])

    async def clear_short_term(self) -> None:
        async with self._lock:
            self._short_term.clear()
