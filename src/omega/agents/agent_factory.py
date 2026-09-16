"""Agent construction and provider-neutral autonomous agent runtime primitives."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


class LLMClient(Protocol):
    async def generate(self, *, system: str, prompt: str, **kwargs: Any) -> str:
        """Generate a response from an LLM provider."""


class MemoryStore(Protocol):
    async def recall(self, query: str, *, limit: int = 5) -> Sequence[Any]:
        """Retrieve relevant memories."""

    async def remember(self, text: str, *, metadata: Mapping[str, Any] | None = None) -> None:
        """Persist a memory."""


class Tool(Protocol):
    name: str

    async def run(self, arguments: Mapping[str, Any]) -> Any:
        """Execute a validated tool call."""


@dataclass(frozen=True, slots=True)
class AgentConfig:
    name: str
    system_prompt: str
    max_iterations: int = 8
    timeout_seconds: float = 120.0
    token_budget: int = 16_000
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Agent name cannot be empty")
        if not self.system_prompt.strip():
            raise ValueError("System prompt cannot be empty")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if self.token_budget < 1:
            raise ValueError("token_budget must be >= 1")


@dataclass(frozen=True, slots=True)
class AgentAction:
    action: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    rationale: str = ""


class AgentProtocolError(ValueError):
    """Raised when an LLM response cannot be converted to a valid agent action."""


class AutonomousAgent:
    """Autonomous agent facade with explicit LLM, memory and tool dependencies."""

    def __init__(self, config: AgentConfig, *, llm: LLMClient, memory: MemoryStore | None, tools: Sequence[Tool]) -> None:
        self.config = config
        self.llm = llm
        self.memory = memory
        self._tools = {tool.name: tool for tool in tools}
        if len(self._tools) != len(tuple(tools)):
            raise ValueError("Tool names must be unique")

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    async def perceive(self, task: str) -> dict[str, Any]:
        if not isinstance(task, str) or not task.strip():
            raise ValueError("Task cannot be empty")
        memories: Sequence[Any] = ()
        if self.memory is not None:
            memories = await self.memory.recall(task, limit=5)
        return {"task": task.strip(), "memories": list(memories)}

    async def plan(self, observation: Mapping[str, Any]) -> AgentAction:
        tools = ", ".join(self.tool_names) if self.tool_names else "none"
        prompt = (
            "You are the planning component of an autonomous agent.\n"
            "Return ONLY a JSON object with exactly these fields: action, arguments, rationale.\n"
            "action must be either 'final' or one of the allowed tools.\n"
            "arguments must be a JSON object.\n"
            f"Allowed tools: {tools}\n\n"
            f"Observation:\n{json.dumps(observation, ensure_ascii=False, default=str)}"
        )
        raw = await self.llm.generate(system=self.config.system_prompt, prompt=prompt)
        return self._parse_action(raw)

    async def execute(self, action: AgentAction) -> Any:
        if action.action == "final":
            return action.rationale
        tool = self._tools.get(action.action)
        if tool is None:
            raise AgentProtocolError(f"Unauthorized tool: {action.action}")
        return await tool.run(action.arguments)

    async def reflect(self, *, observation: Mapping[str, Any], action: AgentAction, result: Any) -> dict[str, Any]:
        prompt = (
            "Assess the latest autonomous step. Return ONLY JSON with fields done and reason.\n"
            "done must be a boolean. Mark done true only when the user's task is satisfied.\n\n"
            f"Observation: {json.dumps(observation, ensure_ascii=False, default=str)}\n"
            f"Action: {json.dumps({'action': action.action, 'arguments': dict(action.arguments), 'rationale': action.rationale}, ensure_ascii=False, default=str)}\n"
            f"Result: {json.dumps(result, ensure_ascii=False, default=str)}"
        )
        raw = await self.llm.generate(system=self.config.system_prompt, prompt=prompt)
        try:
            value = self._decode_json_object(raw)
            done = value.get("done")
            reason = value.get("reason", "")
            if not isinstance(done, bool) or not isinstance(reason, str):
                raise AgentProtocolError("Reflection must contain boolean 'done' and string 'reason'")
            return {"done": done, "reason": reason}
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AgentProtocolError(f"Invalid reflection response: {exc}") from exc

    async def remember(self, text: str, *, metadata: Mapping[str, Any] | None = None) -> None:
        if self.memory is not None and text.strip():
            await self.memory.remember(text.strip(), metadata=metadata)

    @staticmethod
    def _decode_json_object(raw: str) -> dict[str, Any]:
        if not isinstance(raw, str) or not raw.strip():
            raise AgentProtocolError("LLM returned an empty response")
        candidate = raw.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            candidate = "\n".join(lines).strip()
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise AgentProtocolError("No JSON object found in LLM response")
        value = json.loads(candidate[start:end + 1])
        if not isinstance(value, dict):
            raise AgentProtocolError("Expected a JSON object")
        return value

    @classmethod
    def _parse_action(cls, raw: str) -> AgentAction:
        value = cls._decode_json_object(raw)
        action = value.get("action")
        arguments = value.get("arguments", {})
        rationale = value.get("rationale", "")
        if not isinstance(action, str) or not action.strip():
            raise AgentProtocolError("Action must be a non-empty string")
        if not isinstance(arguments, dict):
            raise AgentProtocolError("Arguments must be a JSON object")
        if not isinstance(rationale, str):
            raise AgentProtocolError("Rationale must be a string")
        return AgentAction(action=action.strip(), arguments=arguments, rationale=rationale)


class AgentFactory:
    """Dependency-injected factory for consistently configured OMEGA agents."""

    def __init__(self, *, llm: LLMClient, memory: MemoryStore | None = None, tools: Sequence[Tool] = ()) -> None:
        self._llm = llm
        self._memory = memory
        self._tools = tuple(tools)
        names = [tool.name for tool in self._tools]
        if any(not isinstance(name, str) or not name.strip() for name in names):
            raise ValueError("Every tool must expose a non-empty string name")
        if len(names) != len(set(names)):
            raise ValueError("Tool names must be unique")

    def create(self, config: AgentConfig, *, tools: Sequence[Tool] | None = None, memory: MemoryStore | None = None) -> AutonomousAgent:
        selected_tools = self._tools if tools is None else tuple(tools)
        selected_memory = self._memory if memory is None else memory
        return AutonomousAgent(config, llm=self._llm, memory=selected_memory, tools=selected_tools)

    def create_from_dict(self, config: Mapping[str, Any], *, tools: Sequence[Tool] | None = None, memory: MemoryStore | None = None) -> AutonomousAgent:
        return self.create(AgentConfig(**dict(config)), tools=tools, memory=memory)
