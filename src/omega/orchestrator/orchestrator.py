"""Async autonomous and multi-agent graph runtime for PROJECT OMEGA."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Callable, Mapping

from omega.agents.agent_factory import AgentAction, AutonomousAgent


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(slots=True)
class TokenBudget:
    limit: int
    used: int = 0

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("Token budget must be >= 1")

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def consume(self, text: str) -> int:
        if not isinstance(text, str):
            text = str(text)
        estimate = max(1, (len(text) + 3) // 4)
        self.used += estimate
        return estimate

    def can_continue(self, reserve: int = 1) -> bool:
        return self.remaining >= reserve


@dataclass(slots=True)
class AgentRun:
    run_id: str
    task: str
    status: RunStatus = RunStatus.RUNNING
    iteration: int = 0
    tokens_used: int = 0
    result: Any = None
    error: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AgentNode:
    name: str
    agent: AutonomousAgent
    next_nodes: tuple[str, ...] = ()


EventHandler = Callable[[Mapping[str, Any]], Awaitable[None]]


class OrchestrationError(RuntimeError):
    """Base error for orchestration failures."""


class Orchestrator:
    """Cancellation-aware autonomous runtime with budgets and graph routing."""

    def __init__(self, *, nodes: Mapping[str, AgentNode] | None = None, event_handler: EventHandler | None = None) -> None:
        self._nodes: dict[str, AgentNode] = dict(nodes or {})
        self._event_handler = event_handler

    def register(self, node: AgentNode) -> None:
        if not node.name.strip():
            raise ValueError("Node name cannot be empty")
        if node.name in self._nodes:
            raise ValueError(f"Agent node already registered: {node.name}")
        for target in node.next_nodes:
            if target == node.name:
                raise ValueError(f"Self-loop is not allowed for node: {node.name}")
        self._nodes[node.name] = node

    async def run(self, agent: AutonomousAgent, task: str, *, max_iterations: int | None = None, timeout_seconds: float | None = None, token_budget: int | None = None) -> AgentRun:
        if not task.strip():
            raise ValueError("Task cannot be empty")
        iterations = agent.config.max_iterations if max_iterations is None else max_iterations
        timeout = agent.config.timeout_seconds if timeout_seconds is None else timeout_seconds
        tokens = agent.config.token_budget if token_budget is None else token_budget
        if iterations < 1 or timeout <= 0 or tokens < 1:
            raise ValueError("Invalid execution budget")
        run = AgentRun(run_id=str(uuid.uuid4()), task=task.strip())
        budget = TokenBudget(tokens)
        try:
            await asyncio.wait_for(self._run_loop(run, agent, iterations, budget), timeout=timeout)
            if run.status is RunStatus.RUNNING:
                run.status = RunStatus.COMPLETED
        except asyncio.TimeoutError:
            run.status = RunStatus.TIMEOUT
            run.error = f"Execution exceeded timeout of {timeout:.2f}s"
        except asyncio.CancelledError:
            run.status = RunStatus.CANCELLED
            raise
        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error = f"{type(exc).__name__}: {exc}"
        run.tokens_used = budget.used
        return run

    async def _emit(self, event: Mapping[str, Any]) -> None:
        if self._event_handler is None:
            return
        try:
            await self._event_handler(event)
        except Exception as exc:
            raise OrchestrationError(f"Event handler failed: {type(exc).__name__}: {exc}") from exc

    async def _run_loop(self, run: AgentRun, agent: AutonomousAgent, iterations: int, budget: TokenBudget) -> None:
        observation = await agent.perceive(run.task)
        budget.consume(str(observation))
        for index in range(1, iterations + 1):
            if not budget.can_continue(1):
                run.status = RunStatus.BUDGET_EXHAUSTED
                run.error = f"Token budget exhausted before iteration {index}"
                return
            run.iteration = index
            started = time.perf_counter()
            action: AgentAction | None = None
            try:
                action = await agent.plan(observation)
                budget.consume(action.rationale + str(action.arguments))
                if not budget.can_continue(1):
                    run.status = RunStatus.BUDGET_EXHAUSTED
                    run.error = "Token budget exhausted after planning"
                    return
                result = await agent.execute(action)
                budget.consume(str(result))
                reflection = await agent.reflect(observation=observation, action=action, result=result)
                budget.consume(str(reflection))
                event = {
                    "run_id": run.run_id,
                    "iteration": index,
                    "action": action.action,
                    "result": result,
                    "reflection": reflection,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                    "tokens_used": budget.used,
                    "tokens_remaining": budget.remaining,
                }
                run.trace.append(event)
                await self._emit(event)
                if bool(reflection.get("done")):
                    run.result = result
                    await agent.remember(f"Task: {run.task}\nResult: {result}", metadata={"run_id": run.run_id, "agent": agent.config.name})
                    return
                observation = {"task": run.task, "previous_action": action.action, "previous_result": result, "reflection": reflection}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error_event = {
                    "run_id": run.run_id,
                    "iteration": index,
                    "action": action.action if action else None,
                    "error": f"{type(exc).__name__}: {exc}",
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                }
                run.trace.append(error_event)
                await self._emit(error_event)
                run.status = RunStatus.FAILED
                run.error = error_event["error"]
                return
        run.status = RunStatus.BUDGET_EXHAUSTED
        run.error = f"Iteration budget exhausted ({iterations})"

    async def run_graph(self, *, start_node: str, task: str, max_hops: int = 32) -> list[AgentRun]:
        if start_node not in self._nodes:
            raise KeyError(f"Unknown agent node: {start_node}")
        if max_hops < 1:
            raise ValueError("max_hops must be >= 1")
        results: list[AgentRun] = []
        visited: set[str] = set()
        current = start_node
        for _ in range(max_hops):
            if current in visited:
                raise OrchestrationError(f"Graph cycle detected at node: {current}")
            visited.add(current)
            node = self._nodes[current]
            result = await self.run(node.agent, task)
            results.append(result)
            if result.status is not RunStatus.COMPLETED or not node.next_nodes:
                return results
            missing = [target for target in node.next_nodes if target not in self._nodes]
            if missing:
                raise OrchestrationError(f"Node {current} references missing nodes: {missing}")
            current = node.next_nodes[0]
        raise OrchestrationError(f"Graph exceeded max_hops={max_hops}")
