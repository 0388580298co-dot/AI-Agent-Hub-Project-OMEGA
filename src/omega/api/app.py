"""FastAPI control plane assembled through dependency injection."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from omega.agents.agent_factory import AgentConfig, AgentFactory
from omega.application.run_service import RunService
from omega.domain.models import RunCommand
from omega.infrastructure.repositories import InMemoryRunRepository
from omega.infrastructure.runtime import OMEGAAgentRunner
from omega.llm_models.config import build_gateway
from omega.memory.store import InMemoryMemoryStore
from omega.orchestrator.orchestrator import Orchestrator
from omega.tools.registry import ToolRegistry
from omega.tools.runtime import ToolPermission, build_agent_tools, register_standard_tools


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=100_000)
    agent: str = Field(default="default", min_length=1, max_length=128)


class RunResponse(BaseModel):
    run_id: str
    status: str


repository = InMemoryRunRepository()
memory = InMemoryMemoryStore()
tool_registry = ToolRegistry()
register_standard_tools(tool_registry)
agent_factory = AgentFactory(
    llm=build_gateway(),
    memory=memory,
    tools=build_agent_tools(tool_registry, ToolPermission(frozenset(tool_registry.names()))),
)
runner = OMEGAAgentRunner(
    factory=agent_factory,
    orchestrator=Orchestrator(),
    default_config=AgentConfig(
        name="default",
        system_prompt="You are an autonomous OMEGA agent. Use approved tools only and finish the requested task accurately.",
    ),
)
service = RunService(runner=runner, repository=repository)

app = FastAPI(
    title="PROJECT OMEGA Control Plane",
    version="0.3.0",
    description="Dependency-injected asynchronous control plane for the OMEGA agent runtime.",
    docs_url="/docs",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "omega-control-plane", "version": "0.3.0"}


@app.post("/v1/runs", response_model=RunResponse, status_code=202)
async def create_run(request: RunRequest) -> RunResponse:
    snapshot = await service.submit(RunCommand(prompt=request.prompt, agent=request.agent))
    return RunResponse(run_id=snapshot.run_id, status=snapshot.state.value)


@app.get("/v1/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    snapshot = await service.get(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "run_id": snapshot.run_id,
        "agent": snapshot.command.agent,
        "prompt": snapshot.command.prompt,
        "status": snapshot.state.value,
        "result": snapshot.result,
        "error": snapshot.error,
        "trace": list(snapshot.trace),
    }
