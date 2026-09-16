"""Production-facing tool runtime helpers built on the OMEGA allow-list registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from omega.tools.registry import Tool, ToolRegistry, ToolSpec


@dataclass(frozen=True, slots=True)
class ToolPermission:
    allowed_tools: frozenset[str] = field(default_factory=frozenset)

    def allows(self, name: str) -> bool:
        return name in self.allowed_tools


class RegistryTool:
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
    return tuple(RegistryTool(registry=registry, name=name, permission=permission) for name in registry.names() if permission.allows(name))


def register_standard_tools(registry: ToolRegistry) -> None:
    from omega.tools.registry import SafeCodeExecutionTool, WebSearchTool
    registry.register(WebSearchTool(), ToolSpec(name="web_search", description="Search configured corpus.", input_schema={"type":"object","required":["query"],"properties":{"query":{"type":"string"},"limit":{"type":"integer"}}}, timeout_seconds=5))
    registry.register(SafeCodeExecutionTool(), ToolSpec(name="code_execution", description="Evaluate safe arithmetic.", input_schema={"type":"object","required":["expression"],"properties":{"expression":{"type":"string"}}}, timeout_seconds=5))


def register_extended_tools(registry: ToolRegistry, *, filesystem: Tool, database: Tool, http: Tool, git: Tool) -> None:
    registry.register(filesystem, ToolSpec(name="filesystem", description="Sandboxed file operations.", input_schema={"type":"object","required":["operation","path"],"properties":{"operation":{"type":"string"},"path":{"type":"string"},"content":{"type":"string"}}}, timeout_seconds=10))
    registry.register(database, ToolSpec(name="database", description="Parameterized SQLite statement.", input_schema={"type":"object","required":["query"],"properties":{"query":{"type":"string"},"params":{"type":"array"}}}, timeout_seconds=10))
    registry.register(http, ToolSpec(name="http_request", description="Allow-listed outbound HTTP request.", input_schema={"type":"object","required":["method","url"],"properties":{"method":{"type":"string"},"url":{"type":"string"},"headers":{"type":"object"},"body":{}}}, timeout_seconds=30))
    registry.register(git, ToolSpec(name="git", description="Read-only repository inspection.", input_schema={"type":"object","required":["operation"],"properties":{"operation":{"type":"string"}}}, timeout_seconds=20))
