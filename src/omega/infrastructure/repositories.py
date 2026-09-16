"""Development repository adapters; durable stores implement the same domain port."""
from __future__ import annotations

import asyncio
from typing import Dict

from omega.domain.models import RunSnapshot


class InMemoryRunRepository:
    def __init__(self) -> None:
        self._items: Dict[str, RunSnapshot] = {}
        self._lock = asyncio.Lock()

    async def save(self, snapshot: RunSnapshot) -> None:
        async with self._lock:
            self._items[snapshot.run_id] = snapshot

    async def get(self, run_id: str) -> RunSnapshot | None:
        async with self._lock:
            return self._items.get(run_id)
