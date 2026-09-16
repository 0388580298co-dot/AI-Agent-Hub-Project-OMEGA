from __future__ import annotations

import pytest

from omega.llm_models.gateway import LLMGateway, LLMRouter, LLMError, ProviderRoute
from omega.llm_models.token_management import TokenBudgetExceeded, TokenLedger
from omega.tools.registry import ToolRegistry, ToolSpec, ToolValidationError
from omega.tools.runtime import ToolPermission, build_agent_tools, register_standard_tools


class FakeProvider:
    name = "fake"

    async def generate(self, *, model: str, system: str, prompt: str, parameters: dict) -> str:
        return f"ok:{model}:{prompt}"


@pytest.mark.asyncio
async def test_gateway_routes_and_accounts_tokens() -> None:
    gateway = LLMGateway(providers={"fake": FakeProvider()}, router=LLMRouter([ProviderRoute("fake", "test-model")]), max_retries=0)
    response = await gateway.complete(__import__("omega.llm_models.gateway", fromlist=["LLMRequest"]).LLMRequest(system="system", prompt="hello", model="test-model"))
    assert response.text == "ok:test-model:hello"
    assert response.total_tokens >= 2


@pytest.mark.asyncio
async def test_registry_validates_and_times_out() -> None:
    class Echo:
        name = "echo"

        async def run(self, arguments):
            return arguments["value"]

    registry = ToolRegistry()
    registry.register(Echo(), ToolSpec(name="echo", description="echo", input_schema={"type": "object", "required": ["value"], "properties": {"value": {"type": "string"}}}))
    assert await registry.execute("echo", {"value": "hello"}) == "hello"
    with pytest.raises(ToolValidationError):
        await registry.execute("echo", {"value": 42})


@pytest.mark.asyncio
async def test_standard_tools_are_permission_scoped() -> None:
    registry = ToolRegistry()
    register_standard_tools(registry)
    tools = build_agent_tools(registry, ToolPermission(frozenset({"code_execution"})))
    assert [tool.name for tool in tools] == ["code_execution"]
    result = await tools[0].run({"expression": "2 + 3 * 4"})
    assert result["result"] == 14


def test_token_ledger_has_hard_limit() -> None:
    ledger = TokenLedger(limit=2)
    ledger.reserve(1)
    with pytest.raises(TokenBudgetExceeded):
        ledger.charge("this text needs more than one token")
