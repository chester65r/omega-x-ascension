# Architecture Review

## Executive decision
The requested end state is credible, but deploying 16 agents, Celery, LangGraph, Neo4j, browser automation, multimodal inference, and a sandbox at once would create an untestable distributed monolith. Phase 1 therefore ships as a modular monolith with ports/adapters and explicit domain boundaries. Components split into services only when load, isolation, or ownership data justifies it.

## Weaknesses found and corrections
1. **Sixteen services would be over-engineering.** Agent is a role plus policy, not a process. One runtime hosts typed role profiles.
2. **LangGraph and Celery overlap.** LangGraph owns workflow state. A queue should later transport coarse jobs only; it must not become a second workflow engine.
3. **Redis is not authoritative memory.** It is coordination/working state. PostgreSQL is the system of record.
4. **Automatic model selection cannot guarantee 'best'.** The router uses declared capabilities, health, priority, and observed metrics. Benchmark feedback is a later closed-loop input.
5. **Self-improvement is governance-sensitive.** The Meta Agent may propose versioned changes, never merge or deploy them.
6. **Docker socket execution is unsafe.** The future sandbox must be a separate service with no daemon socket, non-root users, dropped capabilities, resource quotas, network-off defaults, and image allowlists.
7. **Neo4j is premature.** PostgreSQL relational edges are sufficient until graph traversal requirements are measured.
8. **Model hosting is hardware-specific.** The core consumes OpenAI-compatible endpoints; vLLM/Ollama/TGI deployment profiles belong in deployment overlays rather than the domain layer.

## Phase 1 acceptance criteria
- API boots without a model and reports readiness honestly.
- Runs are durable and auditable.
- Every selected model has a declared matching capability.
- Deployment-class work pauses for human approval.
- Domain code has no FastAPI, SQLAlchemy, Redis, or vendor SDK imports.
- Unit tests cover routing and approval policy.

## Known gaps
Authentication, tenant isolation, quota enforcement, encrypted secrets, distributed traces, migrations in the startup path, full LangGraph checkpoint persistence, and a hardened sandbox are required before internet exposure. Phase 1 is deployable for a trusted network, not yet a public multi-tenant SaaS.
