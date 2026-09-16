# PROJECT OMEGA: The Agent Operating System

Open-source foundation for building, orchestrating, evaluating, and deploying autonomous AI agents at scale.

## Architecture

```text
User / API / Dashboard
        |
        v
   Orchestrator  <---->  Event Bus / Observability
        |
   +----+-------------------+
   |                        |
   v                        v
Agent Runtime          Multi-Agent Graph
   |                        |
   +-----> LLM Gateway <----+
   |          |
   |          +--> OpenAI / Anthropic / Local models
   |
   +-----> Tools (Web / Code / DB / APIs)
   |
   +-----> Memory (short-term / vector / long-term)
   |
   +-----> Evaluation / Tracing / Metrics

Dashboard (React/TypeScript) consumes API + realtime events.
```

## Autonomous workflow

`Perceive -> Plan -> Execute -> Reflect -> (repeat or Finish)`

The runtime is intentionally provider-agnostic: LLMs, tools, memory stores, and persistence are injected through interfaces rather than hard-coded into the core loop.

## Repository layout

See `docs/ARCHITECTURE.md` for the detailed architecture and `src/omega/` for the Python runtime foundation.

## Development principles

- Explicit interfaces and dependency injection
- Async-first execution
- Structured state instead of stringly-typed orchestration
- Timeouts and iteration budgets
- Cancellation-aware execution
- Provider/tool isolation
- Observability hooks at orchestration boundaries
- Safe defaults: no unrestricted tool execution in the core runtime

## License

Apache-2.0 (planned).
