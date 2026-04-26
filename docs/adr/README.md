# Architecture Decision Records

Lightweight ADRs for the load-bearing decisions in OmniTrade. The
purpose is to make the *why* behind hard rules legible to future
maintainers — code shows what; this directory shows why.

## Index

- [0001 — Agno as the only LLM / Agent / MCP framework](0001-agno-as-only-agent-framework.md)
- [0002 — Three-way state atomicity for position lifecycle](0002-three-way-state-atomicity.md)

## Format

Adapted from [Michael Nygard's ADR template][nygard]:

```
# ADR NNNN — short title

- **Status**: Proposed | Accepted | Superseded by ADR NNNN
- **Deciders**: …
- **Related** / **Supersedes**: …

## Context
What problem are we solving? What constraints?

## Decision
The decision in one sentence, then the implementation contract.

## Consequences
### Positive
### Negative
### Neutral

## Compliance
How is the decision enforced? CI rules, code locations, hard rules in
CLAUDE.md, …
```

[nygard]: https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
