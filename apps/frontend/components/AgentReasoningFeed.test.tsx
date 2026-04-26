import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AgentReasoningFeed } from "./AgentReasoningFeed";
import { I18nProvider } from "@/lib/i18n/context";
import type { AgentDecision } from "@/lib/api/types";

// Mock useDecisions so tests don't hit the network
vi.mock("@/hooks/useDecisions", () => ({
  useDecisions: vi.fn(),
}));

import { useDecisions } from "@/hooks/useDecisions";
const mockUseDecisions = vi.mocked(useDecisions);

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nProvider>{children}</I18nProvider>;
}

function renderFeed() {
  return render(<AgentReasoningFeed />, { wrapper: Wrapper });
}

const BASE_DECISION: AgentDecision = {
  id: 1,
  timestamp: "2026-04-19T00:00:00Z",
  iteration: 1,
  decision: "hold",
  market_analysis: "{}",
  actions_taken: "[]",
  account_value: "10000",
  positions_count: 0,
  run_id: null,
};

describe("AgentReasoningFeed", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("case legacy: renders blockquote for old decisions (new fields null)", () => {
    const legacyDecision: AgentDecision = {
      ...BASE_DECISION,
      decision: "hold — waiting for clearer setup",
      actions_taken: JSON.stringify([{ tool: "hold", reason: "No edge right now" }]),
      // structured fields absent / null
      structured_confidence: null,
      market_context: null,
      gates_passed: null,
      invalidation_condition: null,
      plan: null,
    };

    mockUseDecisions.mockReturnValue({
      decisions: [legacyDecision],
      count: 1,
      isLoading: false,
      error: undefined,
      mutate: vi.fn(),
      key: "/api/v1/decisions?limit=25&offset=0",
    });

    renderFeed();

    // legacy blockquote must be present
    expect(screen.getByTestId("reasoning-text")).toBeInTheDocument();

    // new structured panels must NOT be present
    expect(screen.queryByTestId("reasoning-panel-market-context")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reasoning-panel-gates")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reasoning-panel-invalidation")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reasoning-panel-plan")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reasoning-panel-confidence")).not.toBeInTheDocument();
  });

  it("case structured-hold: renders structured panels without PlanCard when plan is null", () => {
    const holdDecision: AgentDecision = {
      ...BASE_DECISION,
      decision: "hold",
      actions_taken: JSON.stringify([{ tool: "hold", reason: "Structured hold" }]),
      structured_confidence: 0.5,
      market_context: "BTC is trading sideways in a consolidation range.",
      gates_passed: ["trend_aligned", "no_news"],
      invalidation_condition: "Break below 60k",
      plan: null,
      output_language: "en",
    };

    mockUseDecisions.mockReturnValue({
      decisions: [holdDecision],
      count: 1,
      isLoading: false,
      error: undefined,
      mutate: vi.fn(),
      key: "/api/v1/decisions?limit=25&offset=0",
    });

    renderFeed();

    // structured panels must be present
    expect(screen.getByTestId("reasoning-panel-market-context")).toBeInTheDocument();
    expect(screen.getByTestId("reasoning-panel-gates")).toBeInTheDocument();
    expect(screen.getByTestId("reasoning-panel-invalidation")).toBeInTheDocument();
    expect(screen.getByTestId("reasoning-panel-confidence")).toBeInTheDocument();

    // PlanCard must NOT be present (plan is null)
    expect(screen.queryByTestId("reasoning-panel-plan")).not.toBeInTheDocument();

    // legacy blockquote must NOT be present
    expect(screen.queryByTestId("reasoning-text")).not.toBeInTheDocument();
  });

  it("case structured-open: renders all 5 panels including PlanCard when plan is present", () => {
    const openDecision: AgentDecision = {
      ...BASE_DECISION,
      decision: "open",
      actions_taken: JSON.stringify([{ tool: "open", symbol: "BTCUSDT", side: "long", reason: "Breakout" }]),
      structured_confidence: 0.75,
      market_context: "BTC breaking out of multi-week range on high volume.",
      gates_passed: ["trend_aligned", "volume_spike", "funding_neutral"],
      invalidation_condition: "Close below 62k on 4H",
      plan: {
        entry: 65000,
        stop_loss: 62000,
        take_profit_1: 70000,
        take_profit_2: 75000,
        risk_usd: 200,
        r_multiple_target: 2.5,
      },
      output_language: "en",
    };

    mockUseDecisions.mockReturnValue({
      decisions: [openDecision],
      count: 1,
      isLoading: false,
      error: undefined,
      mutate: vi.fn(),
      key: "/api/v1/decisions?limit=25&offset=0",
    });

    renderFeed();

    // all 5 structured panels must be present
    expect(screen.getByTestId("reasoning-panel-market-context")).toBeInTheDocument();
    expect(screen.getByTestId("reasoning-panel-gates")).toBeInTheDocument();
    expect(screen.getByTestId("reasoning-panel-invalidation")).toBeInTheDocument();
    expect(screen.getByTestId("reasoning-panel-plan")).toBeInTheDocument();
    expect(screen.getByTestId("reasoning-panel-confidence")).toBeInTheDocument();

    // legacy blockquote must NOT be present
    expect(screen.queryByTestId("reasoning-text")).not.toBeInTheDocument();
  });
});
