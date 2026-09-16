"""Framework-independent domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class RunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class RunCommand:
    prompt: str
    agent: str = "default"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("prompt cannot be empty")
        if not self.agent.strip():
            raise ValueError("agent cannot be empty")


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    run_id: str
    command: RunCommand
    state: RunState
    result: Any = None
    error: str | None = None
    trace: tuple[Mapping[str, Any], ...] = ()
