# ADR 0001 — Agno as the only LLM / Agent / MCP framework

- **Status**: Accepted (2026-04-26)
- **Deciders**: maintainers
- **Supersedes**: the LangGraph + LangChain + LiteLLM + mcp2py stack used in the TS-era and early Python rewrite

## Context

OmniTrade started life on a stack of LangGraph (orchestration) +
LangChain (model wrappers + tool wiring) + LiteLLM (provider-agnostic
chat) + mcp2py (MCP client). Each of these added independent versioning
risk, divergent abstractions, and surface area for breakage. The
trading-cycle code path threaded through all four; a bump in any one
needed cassette regeneration in the other three.

We also tried introducing Agno alongside the existing stack as a Stage A
"add it next to" experiment. That immediately ran into:

- Two parallel tool-call serialisation formats (LangChain's
  function-message protocol vs Agno's structured tool messages)
- Two parallel LLM client paths (LiteLLM's provider abstraction vs
  Agno's per-model classes)
- Two retry layers (custom backoff in our application code vs Agno's
  native retry)
- Confusion over whose `Tool` annotations the schema validator should
  follow

By the time we'd reproduced our existing 22-fixture characterisation
gate against the Agno path, we had a clear quantitative answer: Agno
alone covered 100% of what the four-framework stack covered, the cycle
ran in ~30% less wall time on average, and the fixture diff was empty.

## Decision

**Agno 2.x is the only LLM / Agent / MCP framework in this codebase.**

That means:

- `apps/backend/src/omnitrade/agents/` is the only module allowed to
  `import agno`
- `rg "from langgraph|from langchain|import litellm|import mcp2py"
  apps/backend/src/` must return zero hits — enforced by CI
- Tool schemas live in `agents/tools/` and use Agno's pydantic-derived
  schema validator, not LangChain's
- Retries are configured via `Agent(retries=...)` — we do not wrap our
  own backoff
- MCP tool servers are loaded via Agno's `MultiMCPTools`, not via a
  separate `mcp2py` client

## Consequences

### Positive

- One framework's release notes to track
- One retry / streaming / cancellation contract
- One serialisation format for tool calls and responses → cassettes are
  smaller and more diffable
- Native AgentOS integration (Workflow + scheduler + traces) without an
  adapter layer
- Native session-summary memory, knowledge layer, HITL pause primitive
- Span attribution stays clean — OpenInference's `AgnoInstrumentor`
  emits one span per agent run / model call / tool call without
  wrapper-attribution noise

### Negative

- We are now wholly dependent on Agno's release cadence and breaking
  changes. Mitigation: the 22-fixture characterisation gate is the
  early-warning system — any agno bump that changes decisions trips it.
- Some legacy LangChain integrations (specific community tool wrappers
  that don't have Agno equivalents) become unavailable. Mitigation: we
  build them as MCP servers instead, which gives us the same plug-in
  shape but on Agno's contract.

### Neutral

- We give up the *option* of multi-framework comparisons in production
  (e.g., A/B testing LangGraph vs Agno on the same cycle). This is
  fine — that comparison is for migration time, not steady-state ops.

## Compliance

- CI's `Acceptance 4` job enforces the zero-import rule via `rg`
- New PRs that introduce LangGraph / LangChain / LiteLLM / mcp2py
  imports are auto-rejected
- `CLAUDE.md` lists this as one of the project's hard rules
- This ADR ships in the repo for the historical record
