"""Adapters that connect domain use cases to the existing agent/orchestrator runtime."""
from __future__ import annotations

from omega.agents.agent_factory import AgentConfig, AgentFactory, AutonomousAgent
from omega.domain.models import RunCommand, RunSnapshot, RunState
from omega.orchestrator.orchestrator import Orchestrator


class OMEGAAgentRunner:
    """Domain-port adapter; the application layer never imports an LLM vendor or tool implementation."""

    def __init__(self, *, factory: AgentFactory, orchestrator: Orchestrator, default_config: AgentConfig) -> None:
        self._factory = factory
        self._orchestrator = orchestrator
        self._default_config = default_config

    async def run(self, command: RunCommand) -> RunSnapshot:
        config = AgentConfig(
            name=command.agent,
            system_prompt=self._default_config.system_prompt,
            max_iterations=self._default_config.max_iterations,
            timeout_seconds=self._default_config.timeout_seconds,
            token_budget=self._default_config.token_budget,
            metadata={**dict(self._default_config.metadata), **dict(command.metadata)},
        )
        agent: AutonomousAgent = self._factory.create(config)
        execution = await self._orchestrator.run(
            agent,
            command.prompt,
            max_iterations=config.max_iterations,
            timeout_seconds=config.timeout_seconds,
            token_budget=config.token_budget,
        )
        state = RunState.COMPLETED if execution.status.value == "completed" else RunState.FAILED
        return RunSnapshot(
            run_id=execution.run_id,
            command=command,
            state=state,
            result=execution.result,
            error=execution.error,
            trace=tuple(execution.trace),
        )
