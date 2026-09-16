"""Dependency inversion ports; domain code does not know concrete infrastructure."""
from __future__ import annotations

from typing import Awaitable, Callable, Mapping, Protocol

from .models import RunCommand, RunSnapshot


class AgentRunner(Protocol):
    async def run(self, command: RunCommand) -> RunSnapshot:
        raise NotImplementedError


class RunRepository(Protocol):
    async def save(self, snapshot: RunSnapshot) -> None:
        raise NotImplementedError

    async def get(self, run_id: str) -> RunSnapshot | None:
        raise NotImplementedError


EventSink = Callable[[Mapping[str, object]], Awaitable[None]]
