"""Agent Factory for PROJECT OMEGA.

The factory intentionally depends only on small runtime protocols. Concrete LLM,
memory and tool implementations can therefore be swapped without changing an agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


class LLMClient(Protocol):
    async def generate(self, *, system: str, prompt: str, **kwargs: Any) -> str:
        """Generate text from the configured model provider."""


class MemoryStore(Protocol):
    async def recall(self, query: str, *, limit: int = 5) -> Sequence[str]:
        """Retrieve relevant memories."""

    async def remember(self, text: str, *, metadata: Mapping[str, Any] | None = None) -> None:
        """Persist a memory."""


class Tool(Protocol):
    name: str

    async def run(self, arguments: Mapping[str, Any]) -> Any:
        """Execute a validated tool invocation."""


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """Declarative configuration for an OMEGA agent."""

    name: str
    system_prompt: str
    max_iterations: int = 8
    timeout_seconds: float = 120.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Agent name cannot be empty")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")


class AutonomousAgent:
    """Provider-neutral agent facade consumed by the orchestrator."""

    def __init__(
        self,
        config: AgentConfig,
        *,
        llm: LLMClient,
        memory: MemoryStore | None = None,
        tools: Sequence[Tool] = (),
    ) -> None:
        self.config = config
        self.llm = llm
        self.memory = memory
        self.tools = {tool.name: tool for tool in tools}

    async def perceive(self, task: str) -> dict[str, Any]:
        memories: Sequence[str] = ()
        if self.memory is not None:
            memories = await self.memory.recall(task, limit=5)
        return {"task": task, "memories": list(memories)}

    async def plan(self, observation: Mapping[str, Any]) -> dict[str, Any]:
        prompt = (
            "Create the next action for this task. Return JSON with keys "
            "action (tool name or 'final'), arguments, and rationale.\n\n"
            f"Observation:\n{observation}"
        )
        raw = await self.llm.generate(system=self.config.system_prompt, prompt=prompt)
        # Parsing/validation is deliberately delegated to the model adapter in the
        # production implementation. Keeping this boundary explicit avoids hiding
        # provider-specific structured-output behavior inside the orchestrator.
        return {"action": "final", "arguments": {}, "rationale": raw, "raw": raw}

    async def execute(self, plan: Mapping[str, Any]) -> Any:
        action = str(plan.get("action", "final"))
        if action == "final":
            return plan.get("rationale", "")
        tool = self.tools.get(action)
        if tool is None:
            raise ValueError(f"Unknown or unauthorized tool: {action}")
        arguments = plan.get("arguments", {})
        if not isinstance(arguments, Mapping):
            raise TypeError("Tool arguments must be a mapping")
        return await tool.run(arguments)

    async def reflect(self, *, observation: Mapping[str, Any], plan: Mapping[str, Any], result: Any) -> dict[str, Any]:
        prompt = (
            "Reflect on the latest action. Decide whether the task is complete. "
            "Return a concise JSON-like decision with keys done and reason.\n\n"
            f"Observation: {observation}\nPlan: {plan}\nResult: {result}"
        )
        raw = await self.llm.generate(system=self.config.system_prompt, prompt=prompt)
        return {"done": plan.get("action") == "final", "reason": raw}


class AgentFactory:
    """Build configured agents from a small, testable dependency set."""

    def __init__(self, *, llm: LLMClient, memory: MemoryStore | None = None, tools: Sequence[Tool] = ()) -> None:
        self._llm = llm
        self._memory = memory
        self._tools = tuple(tools)

    def create(self, config: AgentConfig) -> AutonomousAgent:
        return AutonomousAgent(
            config,
            llm=self._llm,
            memory=self._memory,
            tools=self._tools,
        )

    def create_from_dict(self, config: Mapping[str, Any]) -> AutonomousAgent:
        """Convenience API: factory.create_from_dict({...})."""
        return self.create(AgentConfig(**dict(config)))
