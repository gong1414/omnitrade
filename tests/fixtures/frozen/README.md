# Frozen Fixtures — Behavioral Baseline Contract

Hand-curated baseline contracts covering the agent's close-path decision surface.
Used by the structured output contract test suite: feed each `market_snapshots/*.json` into the Python agent, diff the output against the matching `baseline_decisions/*.json`. The fixtures remain the ground-truth contracts; regression is now enforced via `tests/agents/test_structured_output_contract.py` (PR-B2 Phase 9).

## Layout

```
tests/fixtures/frozen/
├── README.md                      ← this file
├── market_snapshots/              ← inputs: full per-cycle decision payload
│   ├── snapshot_01_*.json
│   ├── ...
│   └── snapshot_20_*.json
└── baseline_decisions/            ← outputs: tool-call list + state writes
    ├── decision_01_*.json
    ├── ...
    └── decision_20_*.json
```

## Coverage matrix (≥20 snapshots spanning all 5 close paths)

| id | strategy | close_path | trigger_field | notes |
|---|---|---|---|---|
| 01 | arena-swingsmith | trailing_stop | L1 (15→8) | peak 16.2%, fell to 7.8%; autoClose=true |
| 02 | arena-swingsmith | trailing_stop | L2 (30→20) | peak 31%, fell to 19.5% |
| 03 | arena-swingsmith | trailing_stop | L3 (50→35) | peak 52%, fell to 34.1% |
| 04 | arena-scalper | stop_loss | leverage=15 (high band -1.5%) | pnl -1.6% |
| 05 | arena-steward | stop_loss | leverage=6 (mid band -2%) | pnl -2.3% |
| 06 | arena-guardian | stop_loss | leverage=2 (low band -2%) | pnl -2.1% |
| 07 | arena-raider | stop_loss | override active (positions.stop_loss=-1.0) | pnl -1.1%, override wins over band |
| 08 | arena-scalper | partial_profit | stage1 (15→50%) | first hit, partial_close 0→50 |
| 09 | arena-scalper | partial_profit | stage2 (25→50%) | second hit, partial_close 50→100 |
| 10 | arena-swingsmith | partial_profit | stage1 (50→40%) | slow strategy |
| 11 | arena-steward | partial_profit | stage3 (25→100%) | full close after prior stages |
| 12 | arena-rebate-hunter | partial_profit | stage1 tight | high-frequency micro-profit |
| 13 | arena-autopilot | ai_decision | closePosition(100) | AI proactive full close on bearish news |
| 14 | arena-autopilot | ai_decision | closePosition(50) | AI proactive partial scaling out |
| 15 | arena-dual-signal | ai_decision | closePosition(100) | tool call; min-hold satisfied |
| 16 | arena-raider-squad | ai_decision | closePosition after team vote | sub-agents converge to close |
| 17 | arena-scalper | none | openPosition BTC long | open-only, no close |
| 18 | arena-steward | none | openPosition ETH short | open-only, no close |
| 19 | arena-guardian | none | hold | nothing — rejection of all signals |
| 20 | arena-strider | none | hold | flat market, AI stands aside |
| 21 | arena-tribunal | ai_decision | jury verdict → closePosition | partial 50%, post-consensus |
| 22 | arena-swingsmith | trailing_stop | L1 edge | exactly at stopAt boundary (8.00%) |

## Snapshot schema — `market_snapshots/snapshot_NN_*.json`

```json
{
  "id": "snapshot_NN_<label>",
  "captured_at": "ISO 8601 UTC",
  "strategy": "<TradingStrategy>",
  "interval_minutes": 20,
  "iteration": 123,
  "risk_params": { "MAX_LEVERAGE": 25, "MAX_POSITIONS": 5, "MAX_HOLDING_HOURS": 36, "EXTREME_STOP_LOSS_PERCENT": -30 },
  "account_info": { "initialBalance": 1000, "peakBalance": 1400, "totalBalance": 1250, "availableBalance": 800, "returnPercent": 25.0, "sharpeRatio": 1.42 },
  "positions": [ { /* positions row + live mark */ } ],
  "market_data": { "BTC": { "price": ..., "ema20": ..., "macd": ..., "rsi7": ..., "fundingRate": ..., "intradaySeries": {...}, "longerTermContext": {...}, "timeframes": {...} } },
  "news_data": {},
  "external_data": {},
  "trade_history": [ /* last 10 trades */ ],
  "recent_decisions": [],
  "close_path_expected": "trailing_stop | stop_loss | partial_profit | ai_decision | none"
}
```

## Decision schema — `baseline_decisions/decision_NN_*.json`

```json
{
  "case_id": "snapshot_NN_<label>",
  "strategy": "<TradingStrategy>",
  "close_path": "trailing_stop | stop_loss | partial_profit | ai_decision | none",
  "tool_calls": [
    { "tool": "closePosition | openPosition | hold", "args": { "symbol": "BTC", "percentage": 100 } }
  ],
  "state_writes": {
    "positions_updates": [
      { "symbol": "BTC", "cumulative_close_pct": 50, "stop_loss": 3.0, "trailing_peak_pnl_pct": 16.2 }
    ],
    "positions_deletes": ["BTC"],
    "trades_inserts": [ { "symbol": "BTC", "side": "long", "type": "close", "pnl": 24.5, "fee": 0.42 } ],
    "agent_decisions_insert": { "iteration": 123, "trigger": "trailing_stop" }
  },
  "notes": "exercises trailing-stop L3->L2->L1 resolution + close-path dispatch"
}
```

## Python replay contract

1. Load each `market_snapshots/*.json`.
2. Construct the per-cycle decision payload the think-node expects.
3. Invoke the Python agent with **deterministic LLM responses** recorded by VCRPY.
4. Diff tool_calls + state_writes against `baseline_decisions/*.json`.
5. Build fails when any structured output contract assertion in `tests/agents/test_structured_output_contract.py` fails.

## Source authority

Every fixture's `close_path` logic is encoded in `apps/backend/src/omnitrade/domain/services/close_path_classifier.py`; the baseline JSONs are hand-curated contracts derived from those rules.

## Notes on data realism

The snapshots use **illustrative but numerically consistent** values derived from the classifier and monitor arithmetic. The shape, field names, state transitions, and close-path boundary conditions are all authored to reproduce the monitor trigger arithmetic exactly.
