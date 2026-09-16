# Memory Layer

Memory is treated as a first-class subsystem: working context, semantic retrieval and durable storage adapters.

Canonical implementation: `src/omega/memory/`. Persistent/vector backends are intentionally injected rather than coupled to the core runtime.