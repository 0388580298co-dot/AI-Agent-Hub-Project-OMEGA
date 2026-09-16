"""Three-tier memory: compressed short-term, episodic vector memory, and working state."""
from __future__ import annotations
import asyncio, time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from omega.memory.store import MemoryRecord, MemoryStore

@dataclass(slots=True)
class WorkingMemory:
    run_id: str
    values: dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)
    async def set(self, key: str, value: Any) -> None:
        if not key.strip(): raise ValueError("working-memory key cannot be empty")
        self.values[key] = value; self.updated_at = time.time()
    def snapshot(self) -> dict[str, Any]: return dict(self.values)

class ShortTermMemory:
    """Bounded conversation memory with deterministic compression when capacity is exceeded."""
    def __init__(self, *, max_items: int = 32, max_chars: int = 24000) -> None:
        if max_items < 2 or max_chars < 100: raise ValueError("invalid short-term limits")
        self.max_items, self.max_chars = max_items, max_chars; self._items: list[str] = []; self._lock = asyncio.Lock()
    async def add(self, text: str) -> None:
        if not text.strip(): raise ValueError("text cannot be empty")
        async with self._lock:
            self._items.append(text.strip())
            while len(self._items) > self.max_items or sum(map(len,self._items)) > self.max_chars:
                head = self._items[: max(1, len(self._items)//2)]
                summary = self._compress(head); self._items = [f"[compressed context]\n{summary}"] + self._items[len(head):]
    @staticmethod
    def _compress(items: Sequence[str]) -> str:
        text = " ".join(items).replace("\n", " ")
        return text if len(text) <= 4000 else text[:3997] + "..."
    async def context(self) -> tuple[str, ...]:
        async with self._lock: return tuple(self._items)

class EpisodicMemory:
    def __init__(self, store: MemoryStore) -> None: self._store = store
    async def remember(self, event: str, *, metadata: Mapping[str, Any] | None = None) -> None: await self._store.remember(event, metadata=metadata)
    async def search(self, query: str, *, limit: int = 5) -> Sequence[MemoryRecord]: return await self._store.recall(query, limit=limit)

@dataclass(slots=True)
class MultiTierMemory:
    short_term: ShortTermMemory
    episodic: EpisodicMemory
    working: WorkingMemory

    async def remember(self, text: str, *, metadata: Mapping[str, Any] | None = None) -> None:
        await self.short_term.add(text); await self.episodic.remember(text, metadata=metadata)
