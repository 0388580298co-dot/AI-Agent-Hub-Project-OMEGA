"""Production-facing tool runtime helpers built on the OMEGA allow-list registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from omega.tools.registry import Tool, ToolError, ToolRegistry, ToolSpec


@dataclass(frozen=True, slots=True)
class ToolPermission:
    """Per-agent tool permission set."""

    allowed_tools: frozenset[str] = field(default_factory=frozenset)

    def allows(self, name: str) -> bool:
        return name in self.allowed_tools


class RegistryTool:
    """Adapts a registry entry to the agent Tool protocol with authorization."""

    def __init__(self, *, registry: ToolRegistry, name: str, permission: ToolPermission) -> None:
        if name not in registry.names():
            raise KeyError(f"Unknown tool: {name}")
        if not permission.allows(name):
            raise PermissionError(f"Tool is not permitted for this agent: {name}")
        self.name = name
        self._registry = registry

    async def run(self, arguments: Mapping[str, Any]) -> Any:
        return await self._registry.execute(self.name, arguments)


def build_agent_tools(registry: ToolRegistry, permission: ToolPermission) -> tuple[Tool, ...]:
    """Create an immutable tool collection for an agent from explicit permissions."""
    return tuple(RegistryTool(registry=registry, name=name, permission=permission) for name in registry.names() if permission.allows(name))


def register_standard_tools(registry: ToolRegistry) -> None:
    """Register OMEGA's dependency-free baseline tools."""
    from omega.tools.registry import SafeCodeExecutionTool, WebSearchTool

    registry.register(WebSearchTool(), ToolSpec(name="web_search", description="Search the configured OMEGA corpus.", input_schema={"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}}, timeout_seconds=5))
    registry.register(SafeCodeExecutionTool(), ToolSpec(name="code_execution", description="Evaluate a safe arithmetic expression.", input_schema={"type": "object", "required": ["expression"], "properties": {"expression": {"type": "string"}}}, timeout_seconds=5))
