#!/usr/bin/env python3
"""PR-B2 Phase B probe: production prompt validation.

Successor to ``scripts/pr_b2_phase_a_probe.py`` (Phase A, commit a6d2ad7).
Phase A validated the v1 anti-hold design as inlined text in the probe
script. Phase B re-runs the same 32-probe harness but now the system
prompts come from the **production** ``format_system_prompt()`` loader —
this is the ground truth test that the rewrite kept the v1 anti-hold
design and did not regress Gate 3 (hold_rate < 50% per strategy).

Triple gate (per strategy, 16 probes per strategy):

  * **Gate 1 — Contract**: Pydantic round-trip success >= 90%
    (>= 15/16 per strategy).
  * **Gate 2 — Content Quality**: >= 80% probes satisfy all 5 per-probe
    content assertions on ``open_position`` / ``partial_close`` (>= 13/16
    per strategy). ``hold_tool`` / ``close_position`` calls exempt from
    plan/gate fields (same tool-aware revision as Phase A Gate 2).
  * **Gate 3 — Hold Rate**: < 50% per strategy (<= 7/16 hold_tool calls).
  * **Gate 4 — Diversity**: >= 3 distinct tool names across all 32 calls.

Usage::

    # From repo root (where ``.env`` lives):
    source .env
    cd apps/backend && uv run python ../../scripts/pr_b2_phase_b_probe.py

Exit codes: 0 = all gates PASS; 1 = >=1 gate FAIL; 2 = API error.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# apps/backend/src on sys.path so we can import ``omnitrade.*``
_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_SRC = _REPO_ROOT / "apps" / "backend" / "src"
if str(_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(_BACKEND_SRC))

_MODEL = "deepseek/deepseek-chat"


# ---------------------------------------------------------------------------
# Scenarios (8) — identical hand-crafted set from Phase A for byte-for-byte
# comparability. DO NOT modify without re-probing both strategies.
# ---------------------------------------------------------------------------

_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "long_trend_strong",
        "symbol": "BTC_USDT",
        "class": "long_trend",
        "snippet": (
            "BTC_USDT perpetual, 1H timeframe. EMA20 ($75,100) > EMA50 "
            "($73,400) > EMA200 ($69,800) — textbook bull alignment. 4H "
            "trend equally clean (EMA20 > EMA50 > EMA200). RSI(14) = 65, "
            "healthy not exhausted. Volume last 3 candles +40% vs 20-period "
            "SMA. MACD histogram positive and expanding above zero line. "
            "Funding rate +0.008% (neutral). Open interest +14% in 24h. "
            "Current price $75,820. Recent 1H swing low $73,100 (clean stop "
            "zone). ATR(14) $1,480."
        ),
    },
    {
        "name": "long_trend_weak",
        "symbol": "ETH_USDT",
        "class": "long_trend",
        "snippet": (
            "ETH_USDT perpetual, 1H timeframe. EMA20 ($3,645) > EMA50 "
            "($3,590) but EMA50 < EMA200 ($3,720) — short-term bullish "
            "within a larger downtrend. RSI(14) = 58, moderate momentum. "
            "Volume last 4 candles +20% vs 20-period avg. MACD histogram "
            "slightly positive, slope flattening. Funding +0.004%. Current "
            "price $3,660. Recent 1H swing low $3,590. ATR(14) $44. "
            "Borderline setup — conflicting TF bias."
        ),
    },
    {
        "name": "short_trend_strong",
        "symbol": "SOL_USDT",
        "class": "short_trend",
        "snippet": (
            "SOL_USDT perpetual, 1H timeframe. EMA20 ($172.40) < EMA50 "
            "($178.60) < EMA200 ($188.10) — clean bear stack. 4H confirms. "
            "RSI(14) = 32, weak momentum, still room before extreme. Volume "
            "last 3 candles +35% with red bodies (distribution). MACD hist "
            "deepening negative. Funding -0.014% (shorts paying, aggressive "
            "bear bias). Open interest +17%. Current price $170.50. Recent "
            "swing high $180.20 (stop reference). ATR(14) $3.30."
        ),
    },
    {
        "name": "short_trend_weak",
        "symbol": "DOGE_USDT",
        "class": "short_trend",
        "snippet": (
            "DOGE_USDT perpetual, 1H timeframe. EMA20 ($0.152) < EMA50 "
            "($0.158) but EMA50 ~ EMA200 ($0.159) — mixed/weak bearish. "
            "RSI(14) = 42, slight bear momentum. Volume last 4 candles +15% "
            "with mixed bodies. MACD histogram red but near zero line. "
            "Funding -0.003%. Current price $0.151. Recent 1H swing high "
            "$0.158. ATR(14) $0.0028. Soft downtrend, no strong thrust."
        ),
    },
    {
        "name": "volatile_spike",
        "symbol": "BTC_USDT",
        "class": "spike",
        "snippet": (
            "BTC_USDT perpetual, 5m timeframe. Price just spiked +2.5% in "
            "14 minutes on ETF-flow headline, now retesting the breakout "
            "level from below. ATR(14) 3.1x normal on 5m. Volume last 5 "
            "candles +280% vs avg. RSI(14) = 72 (elevated but not extreme). "
            "Funding jumped from +0.006% to +0.028%. Open interest +18% in "
            "20 min. Current price $76,420 (spike high $76,510, prior "
            "resistance $76,200 now tested as support). Order book: bid "
            "wall at $76,100. ATR(14) $950."
        ),
    },
    {
        "name": "post_spike_retest",
        "symbol": "ETH_USDT",
        "class": "spike",
        "snippet": (
            "ETH_USDT perpetual, 15m timeframe. Spiked +3.2% earlier this "
            "session then pulled back to 4H EMA20 support at $3,695. Now "
            "attempting to reclaim the spike midpoint $3,712. Volume on "
            "pullback thinned -30% vs spike candle (healthy absorption). "
            "RSI(14) = 55 (reset from 78). MACD histogram flattened but "
            "still positive. Funding +0.011%. Current price $3,708. ATR(14) "
            "$52. Reclaim attempt is the structural read."
        ),
    },
    {
        "name": "range_narrow",
        "symbol": "LINK_USDT",
        "class": "range",
        "snippet": (
            "LINK_USDT perpetual, 4H timeframe. Tight range $14.20 - $14.38 "
            "(1.3%) for 13 sessions. EMA20/50/200 within 0.2% of each other. "
            "RSI(14) = 51. Volume -42% vs 20-period avg (dead tape). BB "
            "width at 10th percentile of yearly distribution. Funding "
            "+0.000%. Current price $14.27 (mid-range). ATR(14) $0.06. "
            "No catalyst; low-liquidity window."
        ),
    },
    {
        "name": "range_breakout_pending",
        "symbol": "AVAX_USDT",
        "class": "breakout_pending",
        "snippet": (
            "AVAX_USDT perpetual, 1H timeframe. 3-day range $39.20 - $41.80. "
            "Current price $41.65 at upper edge. EMA20 ($40.90) > EMA50 "
            "($40.40) — short-term bias up. RSI(14) = 63, rising. Volume "
            "last 4 candles +55% building into the level. MACD histogram "
            "positive and expanding. Funding +0.012%. ATR(14) $0.68. Bid "
            "stack thick at $41.40; ask thinning above $41.80."
        ),
    },
]

_ACCOUNT_STATES: list[dict[str, Any]] = [
    {
        "name": "flat",
        "description": (
            "Account: $10k USDT, no open positions, risk-budget 1%/trade."
        ),
    },
    {
        "name": "open_long",
        "description": (
            "Account: $10k USDT. Open position: LONG 0.5 BTC @ $74,500 "
            "(current price $76,200, +2.3%, unrealized PnL +$850, 10x "
            "leverage, stop-loss $73,800). Risk-budget 1%/trade for any "
            "new or adjusted position."
        ),
    },
]


# ---------------------------------------------------------------------------
# Tool schemas — identical 4-tool layout to Phase A (hold_tool last).
# ---------------------------------------------------------------------------


def _structured_reason_schema() -> dict[str, Any]:
    from omnitrade.agents.tools.structured_reason import StructuredReason

    schema = StructuredReason.model_json_schema()
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
        # hold_tool LAST to counter ordering bias per Phase A / Pre-Mortem #4 M1.
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
    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY")


def _load_production_minimal_prompts() -> list[tuple[str, str]]:
    """Return ``[(strategy_name, system_prompt), ...]`` rendered via the
    PRODUCTION loader. This is what Phase B validates — same harness as
    Phase A but prompts come from ``format_system_prompt()``.
    """
    from omnitrade.agents.prompts.system import format_system_prompt
    from omnitrade.domain.enums import StrategyName

    # Use Phase A's default interpolation values so gate comparability is
    # preserved. ``strategy_desc`` mirrors Phase A's v1 minimal doc's
    # strategy-context sentence.
    autopilot_desc = (
        "Playbook: single-path trend-follower. Take the cleanest directional "
        "bias across 1H/4H EMAs and trade it with conviction."
    )
    dual_signal_desc = (
        "Playbook: dual-signal — trend AND momentum must agree for full "
        "conviction. Divergence means act on the stronger signal at reduced "
        "size, NEVER abstain on disagreement alone."
    )

    return [
        (
            StrategyName.AI_AUTONOMOUS.value,
            format_system_prompt(
                StrategyName.AI_AUTONOMOUS,
                strategy_desc=autopilot_desc,
            ),
        ),
        (
            StrategyName.ALPHA_BETA.value,
            format_system_prompt(
                StrategyName.ALPHA_BETA,
                strategy_desc=dual_signal_desc,
            ),
        ),
    ]


async def _run_single_probe(
    client: Any,
    strategy_name: str,
    system_prompt: str,
    scenario: dict[str, Any],
    account_state: dict[str, Any],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    user_msg = (
        f"Market snapshot (scenario={scenario['name']}, "
        f"symbol={scenario['symbol']}, account_state={account_state['name']}):\n\n"
        f"{scenario['snippet']}\n\n"
        f"{account_state['description']}\n\n"
        "Call exactly one tool (open_position / close_position / partial_close / "
        "hold_tool) with a full structured `reason`."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    response = await client.complete(
        messages=messages,
        model=_MODEL,
        temperature=0.2,
        tools=tools,
        tool_choice="required",
    )

    choices = response.get("choices") or []
    record: dict[str, Any] = {
        "strategy": strategy_name,
        "scenario": scenario["name"],
        "scenario_class": scenario["class"],
        "account_state": account_state["name"],
        "symbol": scenario["symbol"],
        "temperature": 0.2,
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
    except Exception as exc:  # noqa: BLE001
        record["contract_error"] = f"pydantic validation failed: {exc}"
        return record

    # Content-quality 5 sub-gates — tool-aware (same revision as Phase A).
    fails: list[str] = []
    mc_len = len(sr.market_context)
    if mc_len < 100:
        fails.append(f"market_context_len={mc_len}<100")
    inv_len = len(sr.invalidation_condition)
    if inv_len < 20:
        fails.append(f"invalidation_len={inv_len}<20")
    just_len = len(sr.justification)
    if just_len < 200:
        fails.append(f"justification_len={just_len}<200")

    is_action = tool_name in {"open_position", "partial_close"}
    plan_populated = False
    if is_action:
        gp_ok = any(len(item) >= 5 for item in sr.gates_passed)
        if not sr.gates_passed:
            fails.append("gates_passed empty (action)")
        elif not gp_ok:
            fails.append(
                f"gates_passed all trivial (max_len="
                f"{max((len(x) for x in sr.gates_passed), default=0)})"
            )
        if sr.plan is None:
            fails.append("action tool but plan is None")
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
    else:
        # hold_tool / close_position: plan/gates are legitimately empty/null
        plan_populated = True

    record["content_quality_fails"] = fails
    record["content_quality_pass"] = len(fails) == 0
    record["metrics"] = {
        "market_context_len": mc_len,
        "gates_passed_len": len(sr.gates_passed),
        "gates_passed_max_elem_len": max(
            (len(x) for x in sr.gates_passed), default=0
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
        "acct",
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
            r["account_state"],
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


async def _main() -> int:
    api_key = _get_api_key()
    if not api_key:
        print(
            "ERROR: neither DEEPSEEK_API_KEY nor LLM_API_KEY set. "
            "Run `source .env` from repo root first.",
            file=sys.stderr,
        )
        return 2

    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

    from omnitrade.infrastructure.llm.litellm_client import LiteLLMClient

    client = LiteLLMClient(model=_MODEL, api_key=api_key)
    tools = _build_tool_schemas()

    strategies = _load_production_minimal_prompts()

    all_records: list[dict[str, Any]] = []
    total = len(strategies) * len(_SCENARIOS) * len(_ACCOUNT_STATES)
    print(
        f"Running {total} probes "
        f"({len(strategies)} strategies x {len(_SCENARIOS)} scenarios x "
        f"{len(_ACCOUNT_STATES)} account states) against model={_MODEL}...",
        file=sys.stderr,
    )
    print(
        "Prompts loaded via production format_system_prompt() — Phase B "
        "regression test for anti-hold design preservation.",
        file=sys.stderr,
    )
    run_started = time.monotonic()
    idx = 0
    for strategy_name, system_prompt in strategies:
        for scenario in _SCENARIOS:
            for account_state in _ACCOUNT_STATES:
                idx += 1
                t0 = time.monotonic()
                try:
                    rec = await _run_single_probe(
                        client=client,
                        strategy_name=strategy_name,
                        system_prompt=system_prompt,
                        scenario=scenario,
                        account_state=account_state,
                        tools=tools,
                    )
                except Exception as exc:  # noqa: BLE001
                    exc_type = type(exc).__name__
                    print(
                        f"ERROR: API call failed on {strategy_name}/"
                        f"{scenario['name']}/{account_state['name']}: "
                        f"{exc_type}: {exc}",
                        file=sys.stderr,
                    )
                    return 2
                elapsed = time.monotonic() - t0
                all_records.append(rec)
                print(
                    f"  [{idx:>2}/{total}] ({elapsed:5.1f}s) "
                    f"[{strategy_name}] {scenario['name']}/"
                    f"{account_state['name']} -> tool={rec['tool_name']!r} "
                    f"contract={'Y' if rec['contract_valid'] else 'N'} "
                    f"quality={'Y' if rec['content_quality_pass'] else 'N'}",
                    file=sys.stderr,
                )

    total_elapsed = time.monotonic() - run_started
    print(f"\nAll {total} probes completed in {total_elapsed:.1f}s", file=sys.stderr)

    # -------------------------------------------------------------------
    # Gate evaluation
    # -------------------------------------------------------------------

    per_strategy: dict[str, dict[str, Any]] = {}
    for strategy_name, _ in strategies:
        recs = [r for r in all_records if r["strategy"] == strategy_name]
        per_strategy[strategy_name] = {
            "records": recs,
            "count": len(recs),
            "contract_valid": sum(1 for r in recs if r["contract_valid"]),
            "quality_pass": sum(1 for r in recs if r["content_quality_pass"]),
            "hold": sum(1 for r in recs if r["tool_name"] == "hold_tool"),
        }
        n = per_strategy[strategy_name]["count"]
        per_strategy[strategy_name]["contract_rate"] = (
            per_strategy[strategy_name]["contract_valid"] / n if n else 0.0
        )
        per_strategy[strategy_name]["quality_rate"] = (
            per_strategy[strategy_name]["quality_pass"] / n if n else 0.0
        )
        per_strategy[strategy_name]["hold_rate"] = (
            per_strategy[strategy_name]["hold"] / n if n else 0.0
        )

    unique_tools = sorted(
        {r["tool_name"] for r in all_records if r["tool_name"] is not None}
    )

    gate1_pass = all(v["contract_rate"] >= 0.9 for v in per_strategy.values())
    gate2_pass = all(v["quality_rate"] >= 0.8 for v in per_strategy.values())
    gate3_pass = all(v["hold_rate"] < 0.5 for v in per_strategy.values())
    gate4_pass = len(unique_tools) >= 3

    # Per-scenario-class hold rate diagnostic.
    class_hold_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"hold": 0, "total": 0}
    )
    for r in all_records:
        cls = r["scenario_class"]
        class_hold_counts[cls]["total"] += 1
        if r["tool_name"] == "hold_tool":
            class_hold_counts[cls]["hold"] += 1
    class_hold_rates: dict[str, float] = {
        cls: (v["hold"] / v["total"] if v["total"] else 0.0)
        for cls, v in class_hold_counts.items()
    }

    scenario_hold_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"hold": 0, "total": 0}
    )
    for r in all_records:
        name = r["scenario"]
        scenario_hold_counts[name]["total"] += 1
        if r["tool_name"] == "hold_tool":
            scenario_hold_counts[name]["hold"] += 1

    account_tool_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for r in all_records:
        account_tool_counts[r["account_state"]][r["tool_name"] or "NONE"] += 1

    # -------------------------------------------------------------------
    # Printing
    # -------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("PER-PROBE RESULTS (32 probes)")
    print("=" * 100)
    print(_format_table(all_records))

    print("\n" + "=" * 100)
    print("GATES")
    print("=" * 100)
    for name, v in per_strategy.items():
        print(
            f"  {name}: contract={v['contract_valid']}/{v['count']} "
            f"({v['contract_rate']:.1%}) "
            f"quality={v['quality_pass']}/{v['count']} ({v['quality_rate']:.1%}) "
            f"hold={v['hold']}/{v['count']} ({v['hold_rate']:.1%})"
        )
    print(
        f"Gate 1 (Contract >= 90% per strategy): "
        f"{'PASS' if gate1_pass else 'FAIL'}"
    )
    print(
        f"Gate 2 (Content Quality >= 80% per strategy): "
        f"{'PASS' if gate2_pass else 'FAIL'}"
    )
    print(
        f"Gate 3 (Hold Rate < 50% per strategy): "
        f"{'PASS' if gate3_pass else 'FAIL'}"
    )
    print(
        f"Gate 4 (Unique tools >= 3 across 32 calls): "
        f"unique={unique_tools} count={len(unique_tools)} "
        f"-> {'PASS' if gate4_pass else 'FAIL'}"
    )

    print("\n" + "-" * 100)
    print("Per-scenario-class hold rate (diagnostic, not a gate):")
    print("-" * 100)
    for cls, rate in sorted(class_hold_rates.items()):
        c = class_hold_counts[cls]
        print(f"  {cls:>20}: {c['hold']}/{c['total']} ({rate:.1%})")

    print("\n" + "-" * 100)
    print("Per-scenario hold rate (diagnostic):")
    print("-" * 100)
    for name in sorted(scenario_hold_counts.keys()):
        c = scenario_hold_counts[name]
        print(
            f"  {name:>25}: {c['hold']}/{c['total']} "
            f"({(c['hold'] / c['total'] if c['total'] else 0):.1%})"
        )

    print("\n" + "-" * 100)
    print("Per-account-state tool distribution (diagnostic):")
    print("-" * 100)
    for state in sorted(account_tool_counts.keys()):
        dist = dict(account_tool_counts[state])
        print(f"  {state}: {dist}")

    all_pass = gate1_pass and gate2_pass and gate3_pass and gate4_pass

    summary = {
        "total_probes": len(all_records),
        "wall_time_seconds": round(total_elapsed, 1),
        "model": _MODEL,
        "prompt_source": "production format_system_prompt() (PR-B2 Phase B)",
        "per_strategy": {
            name: {
                "probes": v["count"],
                "contract_valid": v["contract_valid"],
                "contract_rate": v["contract_rate"],
                "quality_pass": v["quality_pass"],
                "quality_rate": v["quality_rate"],
                "hold": v["hold"],
                "hold_rate": v["hold_rate"],
            }
            for name, v in per_strategy.items()
        },
        "unique_tools": unique_tools,
        "gates": {
            "gate1_contract": gate1_pass,
            "gate2_quality": gate2_pass,
            "gate3_hold": gate3_pass,
            "gate4_diversity": gate4_pass,
        },
        "class_hold_rates": class_hold_rates,
        "class_hold_counts": {k: dict(v) for k, v in class_hold_counts.items()},
        "scenario_hold_counts": {k: dict(v) for k, v in scenario_hold_counts.items()},
        "account_tool_counts": {
            k: dict(v) for k, v in account_tool_counts.items()
        },
        "all_pass": all_pass,
    }
    summary_path = _REPO_ROOT / ".omc" / "autopilot" / "pr-b2-phase-b-summary.json"
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
        return 0

    failed = [
        f"gate{i}"
        for i, passed in enumerate(
            [gate1_pass, gate2_pass, gate3_pass, gate4_pass], start=1
        )
        if not passed
    ]
    print(f"\nVERDICT: FAIL (gates={','.join(failed)})")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
