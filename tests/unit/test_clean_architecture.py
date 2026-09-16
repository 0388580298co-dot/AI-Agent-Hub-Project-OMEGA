from __future__ import annotations

import asyncio

from omega.application.run_service import RunService
from omega.domain.models import RunCommand, RunSnapshot, RunState
from omega.infrastructure.repositories import InMemoryRunRepository


class FakeRunner:
    async def run(self, command: RunCommand) -> RunSnapshot:
        return RunSnapshot(run_id="runtime-id", command=command, state=RunState.COMPLETED, result="done")


def test_application_layer_depends_on_ports_not_frameworks():
    async def scenario() -> None:
        repository = InMemoryRunRepository()
        service = RunService(runner=FakeRunner(), repository=repository)
        queued = await service.submit(RunCommand(prompt="hello", agent="tester"))
        assert queued.state is RunState.QUEUED
        await asyncio.sleep(0)
        stored = await service.get(queued.run_id)
        assert stored is not None
        assert stored.state is RunState.COMPLETED
        assert stored.result == "done"

    asyncio.run(scenario())
