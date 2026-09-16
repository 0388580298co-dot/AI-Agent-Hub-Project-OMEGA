from __future__ import annotations
import asyncio
from omega.memory.multi_tier import EpisodicMemory, MultiTierMemory, ShortTermMemory, WorkingMemory
from omega.memory.store import InMemoryMemoryStore
from omega.orchestrator.state_graph import GraphNode, GraphState, StateGraph


def test_three_tier_memory():
    async def scenario():
        store=InMemoryMemoryStore(short_term_limit=4); memory=MultiTierMemory(ShortTermMemory(max_items=4,max_chars=500),EpisodicMemory(store),WorkingMemory("run-1"))
        await memory.remember("project omega uses qdrant")
        await memory.working.set("phase", 4)
        assert memory.working.snapshot()["phase"] == 4
        assert (await memory.episodic.search("qdrant"))
    asyncio.run(scenario())


def test_state_graph_requires_approval_for_sensitive_node():
    async def scenario():
        approvals=[]
        async def approve(request): approvals.append(request.node); return True
        async def step(state): return {"done":True}
        graph=StateGraph(max_steps=2,approval_handler=approve); graph.add_node(GraphNode("safe",step)); graph.add_node(GraphNode("danger",step,sensitive=True)); graph.add_edge("safe","danger")
        result=await graph.run(GraphState("run"),start="safe")
        assert result.data["done"] is True and approvals == ["danger"]
    asyncio.run(scenario())
