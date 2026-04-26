import { test, expect } from "@playwright/test";
import { startFakeSseServer, type FakeSseServer } from "./fixtures/fake-sse-server";

let sse: FakeSseServer;

test.beforeAll(async () => {
  sse = await startFakeSseServer(8765);
});

test.afterAll(async () => {
  if (sse) await sse.close();
});

// ---- REST response fixtures (match Phase 5 Pydantic shapes verbatim) ------

const ACCOUNT_FIXTURE = {
  timestamp: new Date().toISOString(),
  total_value: "10234.56",
  available_cash: "5102.33",
  unrealized_pnl: "132.23",
  realized_pnl: "80.00",
  return_percent: "2.34",
  sharpe_ratio: "1.85",
  peak: "10500.00",
  drawdown_percent: "2.52",
};

const POSITIONS_FIXTURE = {
  positions: [
    {
      id: 1,
      symbol: "BTC_USDT",
      side: "long",
      quantity: "0.015",
      entry_price: "65000.00",
      current_price: "66321.00",
      leverage: 3,
      unrealized_pnl: "19.81",
      stop_loss: "63000.00",
      trailing_peak_pnl_pct: "2.10",
      cumulative_close_pct: "0",
      opened_at: new Date().toISOString(),
      confidence: "0.72",
    },
  ],
  count: 1,
};

const DECISIONS_FIXTURE = {
  decisions: [
    {
      id: 42,
      timestamp: new Date().toISOString(),
      iteration: 7,
      decision: "Open 3x long on BTC_USDT with 2% size",
      market_analysis: "Momentum positive on 4h, funding neutral.",
      actions_taken: "open_long",
      account_value: "10234.56",
      positions_count: 1,
      run_id: "run-abc",
    },
  ],
  count: 1,
  limit: 25,
  offset: 0,
};

const CONFIG_FIXTURE = {
  trading_strategy: "strategy1",
  trading_interval_minutes: 20,
  max_leverage: 10,
  max_positions: 5,
  environment: "test",
};

test.describe("dashboard", () => {
  test("renders + streams a decision update", async ({ page }) => {
    await page.route("**/api/v1/account", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ACCOUNT_FIXTURE) }),
    );
    await page.route("**/api/v1/positions", (r) =>
      r.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(POSITIONS_FIXTURE),
      }),
    );
    await page.route("**/api/v1/decisions*", (r) =>
      r.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(DECISIONS_FIXTURE),
      }),
    );
    await page.route("**/api/v1/config", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(CONFIG_FIXTURE) }),
    );

    await page.goto("/dashboard", { waitUntil: "domcontentloaded" });

    // ── Dark mode default gate (CI-enforced) ───────────────────────────────
    const htmlClass = await page.getAttribute("html", "class");
    expect(htmlClass).toContain("dark");

    // ── LCP measurement (informational) ────────────────────────────────────
    const lcpMs = await page.evaluate(
      () =>
        new Promise<number>((resolve) => {
          let largest = 0;
          const po = new PerformanceObserver((list) => {
            for (const e of list.getEntries()) {
              largest = Math.max(largest, e.startTime);
            }
          });
          try {
            po.observe({ type: "largest-contentful-paint", buffered: true });
          } catch {
            resolve(0);
            return;
          }
          setTimeout(() => {
            po.disconnect();
            resolve(largest);
          }, 2000);
        }),
    );
    console.log(`[perf] LCP=${lcpMs.toFixed(0)}ms (informational, threshold 3000ms)`);

    // ── Initial render assertions ──────────────────────────────────────────
    await expect(page.getByTestId("account-card")).toBeVisible();
    await expect(page.getByTestId("positions-card")).toBeVisible();
    await expect(page.getByTestId("decisions-card")).toBeVisible();
    await expect(page.locator('[data-testid="decision-row"]').first()).toBeVisible();
    await expect(page.locator('[data-testid="position-row"]').first()).toBeVisible();

    // ── SSE-driven new decision row ───────────────────────────────────────
    // Intercept the /decisions revalidation triggered by the SSE event and
    // return a fresh payload whose first row has a distinctive decision text.
    await page.unroute("**/api/v1/decisions*");
    const pushedDecision = {
      decisions: [
        {
          id: 99,
          timestamp: new Date().toISOString(),
          iteration: 8,
          decision: "LIVE-SSE-INJECTED close 50% BTC_USDT",
          market_analysis: "Top-of-range fade trigger.",
          actions_taken: "partial_close",
          account_value: "10400.00",
          positions_count: 1,
          run_id: "run-sse-99",
        },
        ...DECISIONS_FIXTURE.decisions,
      ],
      count: 2,
      limit: 25,
      offset: 0,
    };
    await page.route("**/api/v1/decisions*", (r) =>
      r.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(pushedDecision),
      }),
    );

    sse.push({
      type: "decision_update",
      payload: pushedDecision.decisions[0],
      trace_id: "trace-sse-99",
      ts: new Date().toISOString(),
    });

    await expect(page.locator('[data-testid="decision-row"]').first()).toContainText(
      "LIVE-SSE-INJECTED",
      { timeout: 10_000 },
    );
  });
});
