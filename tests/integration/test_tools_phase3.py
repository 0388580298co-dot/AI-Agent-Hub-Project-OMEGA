from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from omega.tools.database import SQLiteDatabaseTool
from omega.tools.filesystem import SandboxedFilesystemTool
from omega.tools.git import GitInspectionTool
from omega.tools.http_tool import HTTPRequestTool
from omega.tools.registry import ToolRegistry, ToolSpec
from omega.tools.runtime import ToolPermission, build_agent_tools, register_standard_tools


class EchoTool:
    name = "echo"

    async def run(self, arguments):
        return arguments["value"]


def test_registry_authorization_and_standard_tools():
    async def scenario():
        registry = ToolRegistry()
        register_standard_tools(registry)
        registry.register(EchoTool(), ToolSpec(name="echo", description="Echo", input_schema={"type":"object","required":["value"],"properties":{"value":{"type":"string"}}}))
        tools = build_agent_tools(registry, ToolPermission(frozenset({"echo"})))
        assert [tool.name for tool in tools] == ["echo"]
        assert await tools[0].run({"value": "ok"}) == "ok"
    asyncio.run(scenario())


def test_filesystem_is_root_sandboxed():
    async def scenario():
        with tempfile.TemporaryDirectory() as root:
            tool = SandboxedFilesystemTool(root=root)
            await tool.run({"operation": "write", "path": "a.txt", "content": "omega"})
            result = await tool.run({"operation": "read", "path": "a.txt"})
            assert result["content"] == "omega"
    asyncio.run(scenario())


def test_sqlite_parameterized_query():
    async def scenario():
        with tempfile.TemporaryDirectory() as root:
            tool = SQLiteDatabaseTool(database_path=Path(root) / "test.db")
            await tool.run({"query": "CREATE TABLE items(id INTEGER, name TEXT)"})
            await tool.run({"query": "INSERT INTO items VALUES (?, ?)", "params": [1, "omega"]})
            result = await tool.run({"query": "SELECT name FROM items WHERE id = ?", "params": [1]})
            assert result["rows"] == [{"name": "omega"}]
    asyncio.run(scenario())
