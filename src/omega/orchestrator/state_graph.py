"""Bounded state-graph workflow engine with explicit human approval gates."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Mapping

class NodeStatus(str, Enum): PENDING="pending"; RUNNING="running"; WAITING="waiting"; COMPLETED="completed"; FAILED="failed"
@dataclass(slots=True)
class GraphState:
    run_id: str; data: dict[str, Any] = field(default_factory=dict); current: str | None = None; steps: int = 0
@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    run_id: str; node: str; action: str; payload: Mapping[str, Any]
ApprovalHandler = Callable[[ApprovalRequest], Awaitable[bool]]
NodeHandler = Callable[[GraphState], Awaitable[Mapping[str, Any] | None]]
@dataclass(frozen=True, slots=True)
class GraphNode:
    name: str; handler: NodeHandler; sensitive: bool = False

class StateGraph:
    def __init__(self, *, max_steps: int = 50, approval_handler: ApprovalHandler | None = None) -> None:
        if max_steps < 1: raise ValueError("max_steps must be positive")
        self._nodes: dict[str, GraphNode] = {}; self._edges: dict[str, tuple[str,...]] = {}; self._max_steps = max_steps; self._approval = approval_handler
    def add_node(self, node: GraphNode) -> None:
        if node.name in self._nodes: raise ValueError(f"duplicate node: {node.name}")
        self._nodes[node.name] = node
    def add_edge(self, source: str, target: str) -> None:
        if source not in self._nodes or target not in self._nodes: raise KeyError("graph edge references unknown node")
        self._edges[source] = (*self._edges.get(source, ()), target)
    async def run(self, state: GraphState, *, start: str, stop: Callable[[GraphState], bool] | None = None) -> GraphState:
        if start not in self._nodes: raise KeyError(start)
        current = start
        while current:
            if state.steps >= self._max_steps: raise RuntimeError("state graph exceeded max_steps")
            node = self._nodes[current]; state.current = current; state.steps += 1
            if node.sensitive:
                if self._approval is None: raise PermissionError(f"human approval required for sensitive node: {current}")
                approved = await self._approval(ApprovalRequest(state.run_id, current, "execute_sensitive_node", state.data))
                if not approved: raise PermissionError(f"human approval denied for node: {current}")
            result = await node.handler(state)
            if result: state.data.update(result)
            if stop and stop(state): break
            targets = self._edges.get(current, ())
            current = targets[0] if targets else None
        state.current = None
        return state
