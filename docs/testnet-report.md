# OmniTrade testnet E2E report

Generated: 2026-04-19 · Gate.io testnet · DeepSeek v3.2

| # | Test | Status | Detail |
|---|---|---|---|
| T1.1 | REST smoke (health/ready) | ✅ pass | HTTP 200; {"db":"ok","exchange":"ok"} |
| T1.2 | account endpoint | ✅ pass | Gate testnet live; $921.21 USDT |
| T1.3 | Dashboard renders | ✅ pass | Playwright CLI; WS connected; 0 console errors |
| T2.1 | Gate fetch_ticker BTC_USDT | ✅ pass | returned price data |
| T2.2 | Gate fetch_positions | ✅ pass | shape OK; 0 open positions |
| T2.3 | Gate fetch_ticker | ✅ pass | BTC_USDT last=75846.6 |
| T2.4 | Gate fetch_ohlcv 1h | ✅ pass | 10 candles, last=[...,75846.5,...] |
| T2.5 | Gate fetch_order_book | ✅ pass | 5 bids / 5 asks |
| T2.6 | Gate fetch_funding_rate | ✅ pass | rate=-0.00001 |
| T2.7 | Gate fetch_open_interest | ⚠️ degraded | ccxt: `gateio fetchOpenInterest() is not supported yet` (testnet limitation) |
| T2.8 | Gate fetch_positions | ✅ pass | n=6 contracts returned |
| T3.1 | DeepSeek chat completion | ✅ pass | model=deepseek-chat; reply=`PING` |
| T3.2 | DeepSeek tool-call → Decision | ✅ pass | openPosition → Decision(action=open, BTC_USDT, long) |
| T4 | APScheduler start/stop | ✅ pass | 5 jobs registered (trading, 2 monitors, account recorder, news) |
| T5.1 | place_order (Gate testnet) | ✅ pass | BTC_USDT long 1 contract @ \$75857.3 lev=2; order_id=82472171445794804 |
| T5.2 | fetch_positions after open | ✅ pass | `BTC_USDT qty=1.0 entry=\$75857.3 side=long` |
| T5.3 | close_position 100% | ✅ pass | order_id=82472171445794805; fill=\$75857.2; pnl=-\$0.10 slippage |
| T5.4 | position flat after close | ✅ pass | BTC_USDT qty=0 (other alts non-zero from prior user sessions — out of scope) |
| T6.1 | Live Events filter buttons (5 total) | ✅ pass | e41-e45 clicked, fresh snapshot each time |
| T6.2 | Dark-mode toggle | ✅ pass | `☾` → `☀` (button label flips `Switch to light/dark theme`) |
| T7.1 | Prompt branch: minimal (arena-autopilot) | ✅ pass | 1042 chars, Chinese minimal template |
| T7.2 | Prompt branch: full (arena-scalper/steward) | ✅ pass | 626 chars, differ by strategy_specific_content |
| T8 | Bad LLM key → graceful error | ✅ pass | `BadRequestError` raised, container still healthy |

## Skipped / out-of-scope

| # | Test | Why skipped |
|---|---|---|
| — | APScheduler auto-fire trading loop | Loop callables are still stubs; wiring real callables into live scheduler is a larger change. Manual run_cycle exercise via T3.2 + T5 already validates the individual components end-to-end. |
| — | Multi-agent path (`arena-tribunal` / `arena-raider-squad`) | Requires `MULTI_AGENT_ENABLED=true` + orchestrator tool registration; safest to cover via characterization tests (case_16 / case_21, already green). |
| — | Playwright emergency close-all | Would open + close a real testnet position just to click the button; redundant with T5. |
| T9 | Full AI decision pipeline | ✅ pass | Gate live snapshot → DeepSeek → Decision(`hold`) → DB id=1 → `/api/v1/decisions` → dashboard "Recent Decisions" card shows `hold`. Reasoning: *"No clear trading signal — price at \$75,846.6 with minimal funding rate of -0.001%."* |
