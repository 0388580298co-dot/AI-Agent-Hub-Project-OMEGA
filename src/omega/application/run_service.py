"""Application use case for starting and querying agent runs."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from omega.domain.models import RunCommand, RunSnapshot, RunState
from omega.domain.ports import AgentRunner, EventSink, RunRepository


class RunService:
    """Coordinates the use case while depending only on domain ports."""

    def __init__(self, *, runner: AgentRunner, repository: RunRepository, event_sink: EventSink | None = None) -> None:
        self._runner = runner
        self._repository = repository
        self._event_sink = event_sink
        self._tasks: set[asyncio.Task[None]] = set()

    async def submit(self, command: RunCommand) -> RunSnapshot:
        run_id = str(uuid.uuid4())
        queued = RunSnapshot(run_id=run_id, command=command, state=RunState.QUEUED)
        await self._repository.save(queued)
        task = asyncio.create_task(self._execute(run_id, command), name=f"omega-run-{run_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return queued

    async def get(self, run_id: str) -> RunSnapshot | None:
        return await self._repository.get(run_id)

    async def _execute(self, run_id: str, command: RunCommand) -> None:
        await self._save(RunSnapshot(run_id=run_id, command=command, state=RunState.RUNNING))
        try:
            result = await self._runner.run(command)
            completed = RunSnapshot(
                run_id=run_id,
                command=command,
                state=result.state,
                result=result.result,
                error=result.error,
                trace=result.trace,
            )
            await self._save(completed)
        except asyncio.CancelledError:
            await self._save(RunSnapshot(run_id=run_id, command=command, state=RunState.CANCELLED))
            raise
        except Exception as exc:
            await self._save(
                RunSnapshot(
                    run_id=run_id,
                    command=command,
                    state=RunState.FAILED,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    async def _save(self, snapshot: RunSnapshot) -> None:
        await self._repository.save(snapshot)
        if self._event_sink is not None:
            await self._event_sink({"run_id": snapshot.run_id, "state": snapshot.state.value})
