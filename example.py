"""End-to-end deterministic PROJECT OMEGA example.

Run from the repository root after installing the package:
    python example.py

The DemoLLM is intentionally deterministic so the example works without API keys.
Replace it with a real provider adapter in production.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from omega.agents.agent_factory import AgentConfig, AgentFactory
from omega.memory.store import InMemoryMemoryStore
from omega.orchestrator.orchestrator import AgentNode, Orchestrator, RunStatus
from omega.tools.registry import SafeCodeExecutionTool, ToolRegistry, ToolSpec, WebSearchTool


class DemoLLM:
    """Small deterministic LLM adapter used to exercise the real runtime contracts."""

    async def generate(self, *, system: str, prompt: str, **kwargs: Any) -> str:
        lowered = system.lower()
        if "researcher" in lowered and "Create the next action" in prompt:
            if '"previous_result"' not in prompt:
                return json.dumps({
                    "action": "web_search",
                    "arguments": {"query": "autonomous agents multi agent systems", "limit": 3},
                    "rationale": "Retrieve concise evidence before producing the research result.",
                })
            return json.dumps({
                "action": "final",
                "arguments": {},
                "rationale": "Research completed from the available simulated web corpus.",
            })
        if "writer" in lowered and "Create the next action" in prompt:
            return json.dumps({
                "action": "final",
                "arguments": {},
                "rationale": "OMEGA coordinates specialized agents through explicit state, safe tools, memory, budgets, and observable execution graphs.",
            })
        if "Assess the latest autonomous step" in prompt:
            return json.dumps({"done": '"action": "final"' in prompt, "reason": "The current step contains a final response."})
        return json.dumps({"action": "final", "arguments": {}, "rationale": "No action required."})


async def main() -> None:
    llm = DemoLLM()
    memory = InMemoryMemoryStore()

    registry = ToolRegistry()
    registry.register(
        WebSearchTool(),
        ToolSpec(
            name="web_search",
            description="Search the deterministic safe demonstration corpus.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
        ),
    )
    registry.register(
        SafeCodeExecutionTool(),
        ToolSpec(
            name="code_execution",
            description="Evaluate a safe arithmetic expression without executing Python code.",
            input_schema={
                "type": "object",
                "required": ["expression"],
                "properties": {"expression": {"type": "string"}},
            },
        ),
    )

    class RegistryToolAdapter:
        def __init__(self, name: str) -> None:
            self.name = name

        async def run(self, arguments: dict[str, Any]) -> Any:
            return await registry.execute(self.name, arguments)

    factory = AgentFactory(
        llm=llm,
        memory=memory,
        tools=(RegistryToolAdapter("web_search"), RegistryToolAdapter("code_execution")),
    )

    researcher = factory.create(
        AgentConfig(
            name="researcher",
            system_prompt="You are a researcher agent. Find evidence and summarize it.",
            max_iterations=4,
            timeout_seconds=20,
            token_budget=4_000,
        )
    )
    writer = factory.create(
        AgentConfig(
            name="writer",
            system_prompt="You are a writer agent. Turn available research into a concise final answer.",
            max_iterations=2,
            timeout_seconds=20,
            token_budget=3_000,
        )
    )

    async def events(event: dict[str, Any]) -> None:
        print(f"[OMEGA] iteration={event.get('iteration')} action={event.get('action')} tokens={event.get('tokens_used')}")

    orchestrator = Orchestrator(
        nodes={
            "researcher": AgentNode(name="researcher", agent=researcher, next_nodes=("writer",)),
            "writer": AgentNode(name="writer", agent=writer),
        },
        event_handler=events,
    )

    results = await orchestrator.run_graph(
        start_node="researcher",
        task="Research how an Agent Operating System should coordinate autonomous AI agents and produce a concise explanation.",
    )

    for result in results:
        print(f"\nAgent run: {result.run_id}")
        print(f"Status: {result.status}")
        print(f"Iterations: {result.iteration}")
        print(f"Tokens used: {result.tokens_used}")
        if result.error:
            print(f"Error: {result.error}")
        else:
            print(f"Result: {result.result}")

    if not results or results[-1].status is not RunStatus.COMPLETED:
        raise RuntimeError("OMEGA example did not complete successfully")


if __name__ == "__main__":
    asyncio.run(main())
