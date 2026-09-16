"""FastAPI control plane for submitting and inspecting OMEGA runs."""
from __future__ import annotations
import asyncio, uuid
from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as exc: raise RuntimeError("Install omega-agent-os[api] to run the API") from exc

from omega.observability.telemetry import Telemetry

app = FastAPI(title="PROJECT OMEGA Control Plane", version="0.2.0", docs_url="/docs")
telemetry = Telemetry(); runs: dict[str, dict[str, Any]] = {}; tasks: dict[str, asyncio.Task[None]] = {}
class RunRequest(BaseModel): prompt: str = Field(min_length=1, max_length=100_000); agent: str = Field(default="default", min_length=1, max_length=128)
class RunResponse(BaseModel): run_id: str; status: str

@app.get("/health")
async def health() -> dict[str,str]: return {"status":"ok","service":"omega-control-plane"}

@app.post("/v1/runs", response_model=RunResponse, status_code=202)
async def create_run(request: RunRequest) -> RunResponse:
    run_id=str(uuid.uuid4()); runs[run_id]={"run_id":run_id,"agent":request.agent,"prompt":request.prompt,"status":"queued"}
    async def execute() -> None:
        async with telemetry.span("agent.run", attributes={"run_id":run_id,"agent":request.agent}):
            runs[run_id]["status"]="running"; await asyncio.sleep(0); runs[run_id]["status"]="accepted"
    tasks[run_id]=asyncio.create_task(execute()); return RunResponse(run_id=run_id,status="queued")

@app.get("/v1/runs/{run_id}")
async def get_run(run_id: str) -> dict[str,Any]:
    if run_id not in runs: raise HTTPException(404,"run not found")
    return runs[run_id]
