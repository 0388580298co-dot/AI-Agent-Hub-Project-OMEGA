# PROJECT OMEGA — Architecture & Workflow

## 1. Mission

OMEGA is a modular Agent Operating System. Its architecture separates **cognition**, **capabilities**, **context**, and **coordination** so each boundary can evolve independently.

## 2. Runtime domains

- **agents** — agent lifecycle and autonomous cognition (`Perceive → Plan → Execute → Reflect`).
- **orchestrator** — run lifecycle, budgets, cancellation and multi-agent graph coordination.
- **llm_models** — provider adapters, deterministic routing, retries, timeouts and token accounting.
- **tools** — registered capabilities with schemas, authorization and execution limits.
- **memory** — working memory, semantic retrieval and persistence abstractions.
- **evaluation** — behavioral, regression, latency and token-efficiency measurement.
- **dashboard** — future React/TypeScript control plane for operations and observability.

## 3. Agent lifecycle

```text
             ┌───────────┐
             │  PERCEIVE │
             └─────┬─────┘
                   ▼
             ┌───────────┐
             │    PLAN   │
             └─────┬─────┘
                   ▼
             ┌───────────┐
             │  EXECUTE  │──────► Approved Tool
             └─────┬─────┘
                   ▼
             ┌───────────┐
             │  REFLECT  │
             └─────┬─────┘
                   │
             continue / finish
                   │
                   └──────────────► PERCEIVE
```

Every run is bounded by iteration and timeout controls. Cancellation is propagated instead of converted into a normal completion.

## 4. LLM Gateway

The gateway exposes a provider-neutral completion contract. Routing selects an enabled provider/model route by explicit priority. Provider adapters currently include:

- OpenAI-compatible HTTP APIs.
- Anthropic Messages API.
- Local OpenAI-compatible servers such as Ollama/vLLM/LM Studio deployments.

The gateway applies request validation, timeout enforcement, retry backoff and provider-independent token estimation. Applications can inject their own provider implementation through the protocol.

## 5. Tool platform

Tools are privileged capabilities. A tool is registered with a name, description, input schema and execution timeout. Agents receive only explicitly authorized tools.

Current baseline adapters:

| Tool | Security boundary |
|---|---|
| Web search | Configured corpus / injected implementation |
| Safe code | Restricted arithmetic AST execution |
| Filesystem | Injected root sandbox |
| SQLite database | Parameterized single-statement execution |
| HTTP | Explicit host allow-list |
| Git | Read-only inspection |

The platform deliberately does not provide unrestricted host Python execution.

## 6. Memory

Memory is an injected subsystem. The current foundation supports in-process records and vector-style similarity retrieval. Production deployments can replace the backend with a durable database/vector service without changing the agent contract.

## 7. Multi-agent graph

Agents are graph nodes rather than hard-coded peer implementations. A future durable graph engine can add conditional routing, fan-out/fan-in, retries, checkpoints and approval gates around the same agent contract.

```text
                         PLANNER
                       /    |     \
                      ▼     ▼      ▼
                 RESEARCH  CODER  ANALYST
                      \     |      /
                       \    |     /
                        ▼   ▼    ▼
                          REVIEWER
                             │
                             ▼
                          RESULT
```

## 8. Operations architecture

```text
React / CLI / API
       │
       ▼
Control Plane ───────► Run Registry / Events / Metrics
       │
       ▼
Orchestrator ─────────► Agent Graph
   │       │             │
   │       ├────────────► Memory
   │       └────────────► Tool Registry
   │
   ▼
LLM Gateway ──────────► Cloud / Local Providers
```

## 9. Production boundaries

- Secrets are injected from the environment or an external secret manager.
- Capability access is explicit and auditable at the registry boundary.
- Filesystem operations remain inside a resolved sandbox root.
- Outbound HTTP can be constrained by host allow-list.
- Database operations are parameterized.
- Git integration is read-only in the baseline platform.
- Durable checkpoints, distributed workers and a network control plane are separate infrastructure layers rather than hidden assumptions inside the core runtime.

## 10. Implementation status

**Completed:** core agent runtime, LLM gateway, cloud/local provider adapters, token accounting, tool registry, authorization boundary, web/code tools, filesystem/database/HTTP/Git adapters, tests, repository documentation and CI quality workflow.

**Next:** persistent memory, durable graph state, evaluation harness, observability/event bus, API/WebSocket control plane, operations dashboard and distributed workers.
