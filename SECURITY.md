# Security policy

OmniTrade automates real trades on cryptocurrency exchanges. Security
issues here can cause direct financial loss, so we take them seriously
and respond fast.

## Reporting a vulnerability

**Do NOT open a public GitHub issue for security problems.**

Instead, email the maintainers privately at the address on the GitHub
repository page (or use GitHub's
[Private Vulnerability Reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
feature on the repository).

Please include:

- A description of the vulnerability and its impact
- Reproduction steps (an isolated minimal repro is ideal)
- The affected commit / version
- Any mitigations you've already identified

We aim to:

- Acknowledge receipt within **72 hours**
- Provide an initial assessment within **7 days**
- Release a fix or mitigation within **30 days** for critical issues

We'll credit you in the security advisory if you'd like (and you
consent).

## Scope

In-scope:

- Backend (`apps/backend/`)
- Frontend (`apps/frontend/`)
- Docker compose / deployment surface (`docker-compose*.yml`,
  `apps/*/Dockerfile`)
- Default configurations (`.env.example` files)
- LLM agent / tool routing (anything that could cause unintended
  trades)
- Authentication & authorization paths (HITL approve/reject endpoint,
  AgentOS overlay)
- Secret handling and credential leakage

Out-of-scope:

- Vulnerabilities in upstream dependencies (please report those to the
  upstream project; we'll ingest the patch when it lands)
- DoS via excessive LLM token usage on your own API key
- Issues that require physical access to the operator's machine

## Threat model — what we explicitly guard against

- **Phantom positions** — the AI hallucinating positions that don't
  exist on the exchange. Mitigated by the G6 cross-source consistency
  check (decision JSON vs `/api/v1/positions` vs `/api/v1/account`).
  Any disagreement is a bug.
- **Unintended large opens** — T9 HITL pauses opens above
  `HITL_OPEN_SIZE_THRESHOLD_USD` (default $10,000) until an operator
  approves via the dashboard banner. The pause loop is wrapped on the
  `record_open_decision` tool itself, not the API surface, so any new
  open path inherits the gate.
- **Daily loss runaway** — `DailyLossLimiter` rewrites any
  open/close/partial_close to `hold` once today's realized PnL drops
  below `-DAILY_LOSS_CAP_USDT`.
- **Mainnet by accident** — `GATE_USE_TESTNET=true` and
  `OKX_USE_TESTNET=true` are the defaults. The tracker docs and the
  `.env.example` repeatedly call this out.
- **Secret leakage** — `.env`, `.env.local`, `*.production` are all
  in `.gitignore`. CI doesn't echo env values. Logs strip secret
  fields via `structlog` processors.
- **LLM data exfiltration** — the agent is given access to
  `coingecko` / `fear & greed` / `whale alert` / `coinglass` /
  `etherscan` / `lunar crush` style read-only data sources, plus the
  4 decision tools and 9 trading tools. It cannot reach arbitrary
  HTTP endpoints. New MCP servers added to the tool roster get
  reviewed against this contract.

## What you, the operator, must do

Even after our hardening, **you** are responsible for:

- **Never committing `.env` or any file with real credentials.** The
  `.gitignore` blocks the obvious paths, but secrets sneaking into
  test fixtures or commit messages are still your call.
- **Starting on testnet.** `GATE_USE_TESTNET=true` is the default;
  flipping it to `false` is a deliberate decision. Run the system for
  weeks on testnet before any mainnet trial, and start with
  meaningful-but-recoverable balances.
- **Rotating keys after suspected compromise.** If you suspect a leak,
  rotate the affected exchange API key immediately. The per-key
  permissions on Gate / OKX should be set to "trade only, no
  withdraw" by default — withdraws should be locked behind 2FA on the
  exchange side.
- **Reading every cycle's reasoning.** The LLM's `market_context` /
  `gates_passed` / `justification` are a free QA channel. The G5
  fault-phrase post_hook (T3) auto-flags 11 known failure phrases,
  but a careful human is still the last line of defense.
- **Setting `HITL_OPEN_SIZE_THRESHOLD_USD` to your tolerance.**
  Default $10,000 is conservative for a small testnet account but
  may be too high for some users. Lower it to whatever notional you
  want to physically approve for.

## Disclosure history

This file will be updated when security issues are patched.

— Last reviewed 2026-04-26.
