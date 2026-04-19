#!/usr/bin/env python3
"""Step 0 pre-merge probe: DeepSeek V3.2 structured-reasoning compliance.

Gate keeper for Phase 2 prompt-audit modernization (see
``.omc/plans/prompt-audit-modernization.md`` §Step 0 L62-96). Empirically
proves that DeepSeek V3.2 under ``tool_choice="required"`` with 4 tools
(open / close / partial_close / hold) emits nested ``StructuredReason``
objects AND that minimal strategies don't degenerate into hold-spam.

Triple+1 gate:

  * **Gate 1 — Contract**: Pydantic round-trip of ``reason`` payload
    succeeds in >= 90% of 10 probes (>= 9/10).
  * **Gate 2 — Content Quality**: >= 80% of 10 probes satisfy all 5
    per-probe content-quality assertions (>= 8/10).
  * **Gate 3 — Hold Rate**: both ``arena-autopilot`` and
    ``arena-dual-signal`` keep hold_rate < 0.5 across their 5 probes
    (i.e. hold count <= 2 per strategy).
  * **Gate 4 — Diversity**: >= 3 distinct tool names chosen across all
    20 tool calls (10 probes x 2 strategies).

Usage::

    # From repo root (where ``.env`` lives):
    source .env
    cd apps/backend && uv run python ../../scripts/probe_deepseek_structured.py

Exit codes:

  * 0 — all 4 gates PASS. Writes 5 cassette fixtures + stdout report.
  * 1 — >= 1 gate FAIL. Prints which gate(s) + evidence. No cassette writes.
  * 2 — API error (auth / rate-limit / network). Prints diagnostic.

Cost: ~$0.02-0.05 per full run (10 probes x 2 strategies = 20 DeepSeek calls).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# apps/backend/src on sys.path so we can import ``omnitrade.*``
_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_SRC = _REPO_ROOT / "apps" / "backend" / "src"
if str(_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(_BACKEND_SRC))

_FIXTURES_DIR = _REPO_ROOT / "apps" / "backend" / "tests" / "agents" / "fixtures"

_MODEL = "deepseek/deepseek-chat"

# ---------------------------------------------------------------------------
# 5 market scenarios x 2 seeds = 10 distinct inputs per strategy.
# Each scenario is hand-crafted to nudge toward a DIFFERENT tool choice so
# the 20-call diversity assertion (Gate 4) is genuinely tested.
# ---------------------------------------------------------------------------

_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "long_trend",
        "seeds": [
            {
                "symbol": "BTC_USDT",
                "snippet": (
                    "BTC_USDT perpetual, 1H timeframe. EMA20 ($71,820) > EMA50 "
                    "($70,140) > EMA200 ($66,300) — textbook bull alignment. "
                    "RSI(14) = 68, not yet overbought. Volume last 3 candles "
                    "+35% vs 20-period SMA. MACD histogram turning positive "
                    "above zero line. Funding rate 0.008% (neutral longs). "
                    "Open interest +12% in 24h. Current price $72,340. "
                    "Recent swing low $68,200 (valid stop zone). ATR(14) $1,450. "
                    "Account: $10k USDT, no open positions, risk-budget 1%/trade."
                ),
            },
            {
                "symbol": "ETH_USDT",
                "snippet": (
                    "ETH_USDT perpetual, 4H timeframe. EMA20 ($3,620) > EMA50 "
                    "($3,510) > EMA200 ($3,280) — multi-week uptrend intact. "
                    "RSI(14) = 62, healthy momentum. Volume last 5 candles "
                    "+22% vs avg. BB middle rising; price sits upper-third of "
                    "envelope. Funding 0.011% (mildly long-biased). Open "
                    "interest +8%. Current price $3,705. Swing low 3 days ago "
                    "$3,480 (stop reference). ATR(14) $78. Account: $10k USDT, "
                    "no open positions, risk-budget 1%/trade."
                ),
            },
        ],
    },
    {
        "name": "short_trend",
        "seeds": [
            {
                "symbol": "SOL_USDT",
                "snippet": (
                    "SOL_USDT perpetual, 1H timeframe. EMA20 ($178.40) < EMA50 "
                    "($184.60) < EMA200 ($192.10) — bearish stack. RSI(14) = "
                    "38 and falling. Volume last 3 candles +48% with red bodies. "
                    "MACD histogram deepening negative. Funding rate -0.015% "
                    "(shorts paying up — rising bear bias). Open interest +18% "
                    "in 24h. Current price $175.80. Recent swing high $186.90 "
                    "(invalidation). ATR(14) $3.20. Account: $10k USDT, no "
                    "open positions, risk-budget 1%/trade."
                ),
            },
            {
                "symbol": "AVAX_USDT",
                "snippet": (
                    "AVAX_USDT perpetual, 4H timeframe. EMA20 ($38.40) < EMA50 "
                    "($40.90) < EMA200 ($45.30) — downtrend confirmed. RSI(14) "
                    "= 34, weak momentum. Volume last 5 candles +31% with "
                    "distribution pattern. MACD red and widening. Funding "
                    "-0.022%. Open interest +14%. Current price $37.60. Swing "
                    "high last Monday $41.80 (stop zone). ATR(14) $1.15. "
                    "Account: $10k USDT, no open positions, risk-budget 1%/trade."
                ),
            },
        ],
    },
    {
        "name": "range",
        "seeds": [
            {
                "symbol": "LINK_USDT",
                "snippet": (
                    "LINK_USDT perpetual, 1H timeframe. Price oscillating $13.80 "
                    "- $14.60 for 11 sessions. EMA20 flat at $14.20, EMA50 flat "
                    "at $14.15 — no trend. RSI(14) = 52 (neutral). Volume 18% "
                    "BELOW 20-period avg (range contraction). Bollinger Bands "
                    "tight; BB-width near 20-day low. Funding 0.001%. Current "
                    "price $14.18 (mid-range). ATR(14) $0.12. Account: $10k "
                    "USDT, no open positions, risk-budget 1%/trade. Prior "
                    "breakout attempts failed twice this week."
                ),
            },
            {
                "symbol": "DOT_USDT",
                "snippet": (
                    "DOT_USDT perpetual, 1H timeframe. Ranging $6.40 - $6.80 for "
                    "8 sessions. EMA20 ($6.60) and EMA50 ($6.58) flat and "
                    "intertwined. RSI(14) = 48. Volume -22% vs 20-period avg. "
                    "BB-width tightest in 3 weeks. Funding 0.002%. Current "
                    "price $6.58. ATR(14) $0.06. Account: $10k USDT, no open "
                    "positions, risk-budget 1%/trade. No catalyst on macro "
                    "calendar next 48h."
                ),
            },
        ],
    },
    {
        "name": "volatile_spike",
        "seeds": [
            {
                "symbol": "DOGE_USDT",
                "snippet": (
                    "DOGE_USDT perpetual, 5m timeframe. Price jumped +14% in "
                    "22 minutes on surprise headline. ATR(14) spiked to 5.2x "
                    "normal. Volume last 4 candles +380% of avg. RSI(14) = 87 "
                    "(extreme). Funding rate jumped from 0.01% to 0.068% — "
                    "aggressive long crowding. Open interest +31% in 20 min. "
                    "Order book: bid walls thinning, ask side filling. Current "
                    "price $0.148 (up from $0.130). Prev resistance $0.142 "
                    "now support (untested). Account: $10k USDT, no open "
                    "positions, risk-budget 1%/trade."
                ),
            },
            {
                "symbol": "XRP_USDT",
                "snippet": (
                    "XRP_USDT perpetual, 5m timeframe. Flash crash -9% in 14 "
                    "minutes on ETF rejection news. ATR(14) 4.6x normal. "
                    "Volume +420% vs avg. RSI(14) = 19 (extreme oversold). "
                    "Funding flipped from +0.008% to -0.045% (panic shorts). "
                    "Open interest -23% (liquidations). Order book thin both "
                    "sides; spread 3.2x normal. Current price $0.488 (from "
                    "$0.537). Recent support $0.482. Account: $10k USDT, no "
                    "open positions, risk-budget 1%/trade."
                ),
            },
        ],
    },
    {
        "name": "flat",
        "seeds": [
            {
                "symbol": "ADA_USDT",
                "snippet": (
                    "ADA_USDT perpetual, 1H timeframe. Price $0.452 - $0.456 "
                    "for 14 sessions (0.9% range). EMA20, EMA50, EMA200 all "
                    "within 0.3% of each other. RSI(14) = 50. Volume 42% BELOW "
                    "20-period avg (dead tape). BB-width 35th-percentile of "
                    "yearly distribution. Funding 0.000%. Current price $0.454. "
                    "ATR(14) $0.003. Account: $10k USDT, no open positions, "
                    "risk-budget 1%/trade. Weekend, pre-NY session."
                ),
            },
            {
                "symbol": "MATIC_USDT",
                "snippet": (
                    "MATIC_USDT perpetual, 4H timeframe. Price stuck $0.580 - "
                    "$0.588 for 22 hours. EMAs bunched within 0.2%. RSI(14) = "
                    "49. Volume -38% vs 20-period avg. Bollinger %B = 0.51 "
                    "(dead center). Funding 0.000%. Current price $0.584. "
                    "ATR(14) $0.004. Account: $10k USDT, no open positions, "
                    "risk-budget 1%/trade. No news, low-liquidity window."
                ),
            },
        ],
    },
]

# ---------------------------------------------------------------------------
# Prompts — two minimal-strategy variants mirroring arena-autopilot /
# arena-dual-signal. Both are simple English + a tool-choice mandate.
# These simulate the stripped-down system prompts those strategies use today.
# ---------------------------------------------------------------------------

_ARENA_AUTOPILOT_SYSTEM = (
    "You are an autonomous crypto futures trader. Call the right tool based on "
    "market data. Use open_position / close_position / partial_close / "
    "hold_tool. Always supply a structured `reason` object describing your "
    "read of the market, the validation gates you checked, the invalidation "
    "condition that would prove you wrong, the numeric plan (entry / SL / TP), "
    "your confidence, and a written justification. For hold decisions, set "
    "plan=null."
)

_ARENA_DUAL_SIGNAL_SYSTEM = (
    "You are an autonomous crypto futures trader running the dual-signal "
    "strategy: enter only when trend AND momentum agree. Call the right tool: "
    "open_position / close_position / partial_close / hold_tool. For every "
    "tool call, supply a structured `reason` with market_context, "
    "gates_passed (list of the validation checks you ran), "
    "invalidation_condition, plan (entry/stop_loss/take_profit_1/take_profit_2/"
    "risk_usd/r_multiple_target, or null for hold), confidence (0-1), and a "
    "written justification. Be decisive; hold only when NEITHER side has an edge."
)


# ---------------------------------------------------------------------------
# Tool schemas: 4 tools, each with ``reason: StructuredReason`` as a required
# parameter. ``reason`` is expanded via Pydantic ``model_json_schema()``
# and inlined so DeepSeek sees the full nested contract.
# ---------------------------------------------------------------------------


def _structured_reason_schema() -> dict[str, Any]:
    """Return the JSON schema for ``reason`` inlined with ``PlanBlock``."""
    from omnitrade.agents.tools.structured_reason import StructuredReason

    schema = StructuredReason.model_json_schema()
    # Inline $defs into the main schema so OpenAI-shape tool schemas (which
    # don't resolve $ref reliably across providers) can consume it.
    defs = schema.pop("$defs", {})

    def _resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node and node["$ref"].startswith("#/$defs/"):
                target = node["$ref"].split("/")[-1]
                resolved = defs.get(target, {})
                return _resolve({k: v for k, v in resolved.items()})
            return {k: _resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_resolve(item) for item in node]
        return node

    return _resolve(schema)


def _build_tool_schemas() -> list[dict[str, Any]]:
    reason_schema = _structured_reason_schema()

    def _fn(
        name: str,
        description: str,
        extra_props: dict[str, Any],
        extra_required: list[str],
    ) -> dict[str, Any]:
        properties: dict[str, Any] = {**extra_props, "reason": reason_schema}
        required = [*extra_required, "reason"]
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    return [
        _fn(
            "open_position",
            "Open a new leveraged futures position.",
            {
                "symbol": {"type": "string"},
                "side": {"type": "string", "enum": ["long", "short"]},
                "size": {"type": "number"},
                "leverage": {"type": "integer"},
                "stop_loss": {"type": "number"},
                "take_profit": {"type": "number"},
            },
            ["symbol", "side", "size", "leverage"],
        ),
        _fn(
            "close_position",
            "Fully close an open position (100%).",
            {"symbol": {"type": "string"}},
            ["symbol"],
        ),
        _fn(
            "partial_close",
            "Partially close an open position (0 < pct <= 100).",
            {
                "symbol": {"type": "string"},
                "percentage": {"type": "number"},
            },
            ["symbol", "percentage"],
        ),
        # hold_tool LAST to counter LLM ordering bias per Pre-Mortem #4 / M1.
        _fn(
            "hold_tool",
            "Take no new action this cycle; maintain current portfolio state.",
            {},
            [],
        ),
    ]


# ---------------------------------------------------------------------------
# Probe execution
# ---------------------------------------------------------------------------


def _get_api_key() -> str | None:
    return (
        os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("LLM_API_KEY")
    )


async def _run_single_probe(
    client: Any,
    system_prompt: str,
    scenario: dict[str, Any],
    seed: dict[str, Any],
    tools: list[dict[str, Any]],
    seed_index: int,
) -> dict[str, Any]:
    """Run one probe and return a normalized record."""
    user_msg = (
        f"Market snapshot (scenario={scenario['name']}, symbol={seed['symbol']}):\n\n"
        f"{seed['snippet']}\n\n"
        "Call exactly one tool (open_position / close_position / partial_close / "
        "hold_tool) with a full structured `reason`."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    # Alternate temperatures on seed 1/2 to mimic 2-seed diversification.
    temperature = 0.2 if seed_index == 0 else 0.6

    response = await client.complete(
        messages=messages,
        model=_MODEL,
        temperature=temperature,
        tools=tools,
        tool_choice="required",
    )

    choices = response.get("choices") or []
    record: dict[str, Any] = {
        "scenario": scenario["name"],
        "seed": seed_index + 1,
        "symbol": seed["symbol"],
        "temperature": temperature,
        "tool_name": None,
        "tool_args_raw": None,
        "tool_args_parsed": None,
        "contract_valid": False,
        "contract_error": None,
        "reason_payload": None,
        "content_quality_pass": False,
        "content_quality_fails": [],
        "metrics": {},
    }
    if not choices:
        record["contract_error"] = "no choices in response"
        return record

    msg = choices[0].get("message") or {}
    tool_calls = msg.get("tool_calls") or []
    if not tool_calls:
        record["contract_error"] = "no tool_calls in response"
        record["message_content"] = msg.get("content")
        return record

    first = tool_calls[0]
    fn = first.get("function") or {}
    tool_name = fn.get("name", "")
    raw_args = fn.get("arguments")
    record["tool_name"] = tool_name
    record["tool_args_raw"] = raw_args

    try:
        parsed_args = (
            json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
        )
    except (json.JSONDecodeError, TypeError) as exc:
        record["contract_error"] = f"args json parse failed: {exc}"
        return record

    record["tool_args_parsed"] = parsed_args

    reason_payload = parsed_args.get("reason")
    record["reason_payload"] = reason_payload

    if reason_payload is None:
        record["contract_error"] = "missing 'reason' in tool args"
        return record

    try:
        from omnitrade.agents.tools.structured_reason import StructuredReason

        sr = StructuredReason.model_validate(reason_payload)
        record["contract_valid"] = True
    except Exception as exc:  # noqa: BLE001 — wide net intentional
        record["contract_error"] = f"pydantic validation failed: {exc}"
        return record

    # Content-quality 5 sub-gates
    fails: list[str] = []
    mc_len = len(sr.market_context)
    if mc_len < 100:
        fails.append(f"market_context_len={mc_len}<100")
    gp_ok = any(len(item) >= 5 for item in sr.gates_passed)
    if not sr.gates_passed:
        fails.append("gates_passed empty")
    elif not gp_ok:
        fails.append(
            f"gates_passed all trivial (max_len="
            f"{max((len(x) for x in sr.gates_passed), default=0)})"
        )
    inv_len = len(sr.invalidation_condition)
    if inv_len < 20:
        fails.append(f"invalidation_len={inv_len}<20")
    is_hold = tool_name == "hold_tool"
    plan_populated = False
    if is_hold:
        plan_populated = True  # Rule vacuously satisfied for hold
    else:
        if sr.plan is None:
            fails.append("non-hold but plan is None")
        else:
            p = sr.plan
            non_zero = (
                (p.entry or 0) != 0
                and (p.stop_loss or 0) != 0
                and (p.take_profit_1 or 0) != 0
            )
            plan_populated = non_zero
            if not non_zero:
                fails.append(
                    f"plan missing non-zero entry/SL/TP1 (entry={p.entry}, "
                    f"sl={p.stop_loss}, tp1={p.take_profit_1})"
                )
    just_len = len(sr.justification)
    if just_len < 200:
        fails.append(f"justification_len={just_len}<200")

    record["content_quality_fails"] = fails
    record["content_quality_pass"] = len(fails) == 0
    record["metrics"] = {
        "market_context_len": mc_len,
        "gates_passed_len": len(sr.gates_passed),
        "gates_passed_max_elem_len": (
            max((len(x) for x in sr.gates_passed), default=0)
        ),
        "invalidation_len": inv_len,
        "justification_len": just_len,
        "plan_populated": plan_populated,
        "confidence": sr.confidence,
    }
    return record


def _format_table(rows: list[dict[str, Any]]) -> str:
    headers = [
        "strategy",
        "scenario",
        "seed",
        "tool",
        "contract",
        "quality",
        "mc_len",
        "gates",
        "inv_len",
        "just_len",
        "plan",
    ]
    widths = {h: len(h) for h in headers}
    out_rows: list[list[str]] = []
    for r in rows:
        row = [
            r["strategy"],
            r["scenario"],
            str(r["seed"]),
            (r["tool_name"] or "NONE"),
            "Y" if r["contract_valid"] else "N",
            "Y" if r["content_quality_pass"] else "N",
            str(r.get("metrics", {}).get("market_context_len", "-")),
            str(r.get("metrics", {}).get("gates_passed_len", "-")),
            str(r.get("metrics", {}).get("invalidation_len", "-")),
            str(r.get("metrics", {}).get("justification_len", "-")),
            "Y" if r.get("metrics", {}).get("plan_populated") else "N",
        ]
        out_rows.append(row)
        for h, cell in zip(headers, row):
            widths[h] = max(widths[h], len(cell))
    sep = "  "
    lines = [sep.join(h.ljust(widths[h]) for h in headers)]
    lines.append(sep.join("-" * widths[h] for h in headers))
    for row in out_rows:
        lines.append(sep.join(cell.ljust(widths[h]) for h, cell in zip(headers, row)))
    return "\n".join(lines)


def _write_cassettes(records: list[dict[str, Any]]) -> list[Path]:
    """Write 5 cassettes — arena-autopilot seed=1 for each of the 5 scenarios."""
    _FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for r in records:
        if r["strategy"] != "arena-autopilot" or r["seed"] != 1:
            continue
        path = _FIXTURES_DIR / f"deepseek_probe_{r['scenario']}_s1.json"
        body = {
            "scenario": r["scenario"],
            "prompt_strategy": "arena-autopilot",
            "model": _MODEL,
            "symbol": r["symbol"],
            "temperature": r["temperature"],
            "tool_calls": [
                {
                    "name": r["tool_name"],
                    "arguments": r["tool_args_parsed"],
                }
            ],
            "contract_valid": r["contract_valid"],
            "content_quality_pass": r["content_quality_pass"],
            "metrics": r.get("metrics", {}),
        }
        with path.open("w", encoding="utf-8") as fh:
            json.dump(body, fh, indent=2, ensure_ascii=False, default=str)
        written.append(path)
    return written


async def _main() -> int:
    api_key = _get_api_key()
    if not api_key:
        print(
            "ERROR: neither DEEPSEEK_API_KEY nor LLM_API_KEY set in environment. "
            "Run `source .env` from repo root first.",
            file=sys.stderr,
        )
        return 2

    # Silence litellm's noisy cost-map fetch warnings — not needed for this script.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

    from omnitrade.infrastructure.llm.litellm_client import LiteLLMClient

    client = LiteLLMClient(model=_MODEL, api_key=api_key)
    tools = _build_tool_schemas()

    strategies = [
        ("arena-autopilot", _ARENA_AUTOPILOT_SYSTEM),
        ("arena-dual-signal", _ARENA_DUAL_SIGNAL_SYSTEM),
    ]

    all_records: list[dict[str, Any]] = []
    print(
        f"Running 10 probes x 2 strategies = 20 DeepSeek tool calls... "
        f"(model={_MODEL})",
        file=sys.stderr,
    )
    for strategy_name, system_prompt in strategies:
        for scenario in _SCENARIOS:
            for seed_idx, seed in enumerate(scenario["seeds"]):
                try:
                    rec = await _run_single_probe(
                        client=client,
                        system_prompt=system_prompt,
                        scenario=scenario,
                        seed=seed,
                        tools=tools,
                        seed_index=seed_idx,
                    )
                except Exception as exc:  # noqa: BLE001
                    exc_type = type(exc).__name__
                    print(
                        f"ERROR: API call failed on {strategy_name}/"
                        f"{scenario['name']}/seed={seed_idx+1}: {exc_type}: {exc}",
                        file=sys.stderr,
                    )
                    return 2
                rec["strategy"] = strategy_name
                all_records.append(rec)
                print(
                    f"  [{strategy_name}] {scenario['name']}/seed={seed_idx+1} "
                    f"-> tool={rec['tool_name']!r} "
                    f"contract={'Y' if rec['contract_valid'] else 'N'} "
                    f"quality={'Y' if rec['content_quality_pass'] else 'N'}",
                    file=sys.stderr,
                )

    # -------------------------------------------------------------------
    # Gates evaluation
    # -------------------------------------------------------------------

    contract_valid_total = sum(1 for r in all_records if r["contract_valid"])
    quality_pass_total = sum(1 for r in all_records if r["content_quality_pass"])
    total_probes = len(all_records)  # 20

    # Per-strategy per-probe-count (10 probes per strategy)
    autopilot_records = [r for r in all_records if r["strategy"] == "arena-autopilot"]
    dualsig_records = [r for r in all_records if r["strategy"] == "arena-dual-signal"]
    autopilot_probe_count = len(autopilot_records)  # 10
    dualsig_probe_count = len(dualsig_records)  # 10

    autopilot_contract_valid = sum(1 for r in autopilot_records if r["contract_valid"])
    dualsig_contract_valid = sum(1 for r in dualsig_records if r["contract_valid"])
    autopilot_quality_pass = sum(1 for r in autopilot_records if r["content_quality_pass"])
    dualsig_quality_pass = sum(1 for r in dualsig_records if r["content_quality_pass"])

    # Hold rate per strategy (spec wording: "5 probes 中 hold 选择数 ≤ 2" i.e.
    # hold_rate < 0.5). We interpret 10 probes per strategy == same threshold:
    # fail if hold_count/strategy_total >= 0.5. The plan §Step 0 L89 explicitly
    # defines hold_rate_minimal_autopilot = (hold calls) / 5 — but the user's
    # task doc says 10 probes per strategy (5 scenarios x 2 seeds). We use
    # the 10-probe denominator and fail if hold_rate >= 0.5.
    autopilot_hold = sum(1 for r in autopilot_records if r["tool_name"] == "hold_tool")
    dualsig_hold = sum(1 for r in dualsig_records if r["tool_name"] == "hold_tool")
    autopilot_hold_rate = (
        autopilot_hold / autopilot_probe_count if autopilot_probe_count else 0.0
    )
    dualsig_hold_rate = (
        dualsig_hold / dualsig_probe_count if dualsig_probe_count else 0.0
    )

    unique_tools = sorted({
        r["tool_name"] for r in all_records if r["tool_name"] is not None
    })

    # Gate thresholds (user task description):
    #   Gate 1 (Contract):      contract_valid / 10 >= 0.9   per-strategy
    #   Gate 2 (Content Qual):  quality_pass / 10 >= 0.8     per-strategy
    #   Gate 3 (Hold Rate):     hold_rate < 0.5              per-strategy
    #   Gate 4 (Diversity):     len(unique_tools) >= 3       across 20 calls
    # The user's "10 probes" = the full 20 calls per gate is ambiguous; we
    # apply gates PER STRATEGY for Gates 1/2/3 (stricter, since the plan
    # explicitly runs 5-per-strategy). Gate 4 is across all 20.

    gate1_autopilot_pass = autopilot_contract_valid / max(autopilot_probe_count, 1) >= 0.9
    gate1_dualsig_pass = dualsig_contract_valid / max(dualsig_probe_count, 1) >= 0.9
    gate1_pass = gate1_autopilot_pass and gate1_dualsig_pass

    gate2_autopilot_pass = autopilot_quality_pass / max(autopilot_probe_count, 1) >= 0.8
    gate2_dualsig_pass = dualsig_quality_pass / max(dualsig_probe_count, 1) >= 0.8
    gate2_pass = gate2_autopilot_pass and gate2_dualsig_pass

    gate3_autopilot_pass = autopilot_hold_rate < 0.5
    gate3_dualsig_pass = dualsig_hold_rate < 0.5
    gate3_pass = gate3_autopilot_pass and gate3_dualsig_pass

    gate4_pass = len(unique_tools) >= 3

    print("\n" + "=" * 88)
    print("PER-PROBE RESULTS")
    print("=" * 88)
    print(_format_table(all_records))

    print("\n" + "=" * 88)
    print("GATES")
    print("=" * 88)
    print(
        f"Gate 1 (Contract valid >= 90% per strategy): "
        f"autopilot={autopilot_contract_valid}/{autopilot_probe_count} "
        f"dual-signal={dualsig_contract_valid}/{dualsig_probe_count} "
        f"-> {'PASS' if gate1_pass else 'FAIL'}"
    )
    print(
        f"Gate 2 (Content quality >= 80% per strategy): "
        f"autopilot={autopilot_quality_pass}/{autopilot_probe_count} "
        f"dual-signal={dualsig_quality_pass}/{dualsig_probe_count} "
        f"-> {'PASS' if gate2_pass else 'FAIL'}"
    )
    print(
        f"Gate 3 (Hold rate < 50% per strategy): "
        f"autopilot={autopilot_hold}/{autopilot_probe_count}="
        f"{autopilot_hold_rate:.1%} "
        f"dual-signal={dualsig_hold}/{dualsig_probe_count}="
        f"{dualsig_hold_rate:.1%} "
        f"-> {'PASS' if gate3_pass else 'FAIL'}"
    )
    print(
        f"Gate 4 (Unique tools across 20 calls >= 3): "
        f"unique={unique_tools} count={len(unique_tools)} "
        f"-> {'PASS' if gate4_pass else 'FAIL'}"
    )

    all_pass = gate1_pass and gate2_pass and gate3_pass and gate4_pass

    # Dump a machine-readable summary for the report.
    summary = {
        "total_probes": total_probes,
        "contract_valid_total": contract_valid_total,
        "quality_pass_total": quality_pass_total,
        "per_strategy": {
            "arena-autopilot": {
                "probes": autopilot_probe_count,
                "contract_valid": autopilot_contract_valid,
                "quality_pass": autopilot_quality_pass,
                "hold": autopilot_hold,
                "hold_rate": autopilot_hold_rate,
            },
            "arena-dual-signal": {
                "probes": dualsig_probe_count,
                "contract_valid": dualsig_contract_valid,
                "quality_pass": dualsig_quality_pass,
                "hold": dualsig_hold,
                "hold_rate": dualsig_hold_rate,
            },
        },
        "unique_tools": unique_tools,
        "gates": {
            "gate1_contract": gate1_pass,
            "gate2_quality": gate2_pass,
            "gate3_hold": gate3_pass,
            "gate4_diversity": gate4_pass,
        },
        "all_pass": all_pass,
    }
    summary_path = _REPO_ROOT / ".omc" / "autopilot" / "step-0-summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {"summary": summary, "records": all_records},
            fh,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    print(f"\nSummary JSON written to {summary_path}")

    if all_pass:
        print("\nVERDICT: PASS (all 4 gates green)")
        written = _write_cassettes(all_records)
        print(f"Wrote {len(written)} cassettes:")
        for p in written:
            print(f"  - {p}")
        return 0

    failed = [
        f"gate{i}"
        for i, passed in enumerate(
            [gate1_pass, gate2_pass, gate3_pass, gate4_pass], start=1
        )
        if not passed
    ]
    print(f"\nVERDICT: FAIL (gates={','.join(failed)}) — NOT writing cassettes")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
