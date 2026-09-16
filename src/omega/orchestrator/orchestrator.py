"""Core autonomous and multi-agent orchestration runtime for PROJECT OMEGA."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Sequence

from omega.agents.agent_factory import AutonomousAgent


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass(slots=True)
class AgentRun:
    run_id: str
    task: str
    status: RunStatus = RunStatus.RUNNING
    iteration: int = 0
    result: Any = None
    error: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AgentNode:
    name: str
    agent: AutonomousAgent
    next_nodes: tuple[str, ...] = ()


class Orchestrator:
    """Executes an agent loop and provides a foundation for graph orchestration.

    Production integrations can subscribe to trace events, persist checkpoints,
    and add policy/authorization around tool execution without changing the loop.
    """

    def __init__(self, *, nodes: Mapping[str, AgentNode] | None = None) -> None:
        self._nodes: dict[str, AgentNode] = dict(nodes or {})

    def register(self, node: AgentNode) -> None:
        if node.name in self._nodes:
            raise ValueError(f"Agent node already registered: {node.name}")
        self._nodes[node.name] = node

    async def run(
        self,
        agent: AutonomousAgent,
        task: str,
        *,
        max_iterations: int | None = None,
        timeout_seconds: float | None = None,
    ) -> AgentRun:
        run = AgentRun(run_id=str(uuid.uuid4()), task=task)
        budget = max_iterations or agent.config.max_iterations
        timeout = timeout_seconds or agent.config.timeout_seconds

        try:
            await asyncio.wait_for(self._run_loop(run, agent, budget), timeout=timeout)
            if run.status is RunStatus.RUNNING:
                run.status = RunStatus.COMPLETED
        except asyncio.TimeoutError:
            run.status = RunStatus.TIMEOUT
            run.error = f"Run exceeded timeout of {timeout:.2f}s"
        except asyncio.CancelledError:
            run.status = RunStatus.CANCELLED
            raise
        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error = f"{type(exc).__name__}: {exc}"
        return run

    async def _run_loop(self, run: AgentRun, agent: AutonomousAgent, budget: int) -> None:
        observation = await agent.perceive(run.task)

        for iteration in range(1, budget + 1):
            run.iteration = iteration
            started = time.perf_counter()

            plan = await agent.plan(observation)
            result = await agent.execute(plan)
            reflection = await agent.reflect(
                observation=observation,
                plan=plan,
                result=result,
            )

            event = {
                "run_id": run.run_id,
                "iteration": iteration,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "plan": plan,
                "result": result,
                "reflection": reflection,
            }
            run.trace.append(event)

            if bool(reflection.get("done")):
                run.result = result
                return

            # The observation is deliberately structured so future implementations
            # can add tool results, retrieved memories, environment state, etc.
            observation = {
                "task": run.task,
                "previous": event,
            }

        run.status = RunStatus.FAILED
        run.error = f"Iteration budget exhausted ({budget})"

    async def run_graph(self, *, start_node: str, task: str) -> list[AgentRun]:
        """Run a simple sequential graph; conditional/fan-out routing is planned next."""
        if start_node not in self._nodes:
            raise KeyError(f"Unknown agent node: {start_node}")

        results: list[AgentRun] = []
        current = start_node
        while current:
            node = self._nodes[current]
            result = await self.run(node.agent, task)
            results.append(result)
            if result.status is not RunStatus.COMPLETED or not node.next_nodes:
                break
            current = node.next_nodes[0]
        return results
