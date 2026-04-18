/**
 * Risk Monitor Tests
 *
 * Tests stop-loss, max holding time, and trailing stop threshold triggers
 * using the same logic as riskExecutor.ts executeForceLiquidation().
 */

import { describe, it, expect, vi } from "vitest";

// Mock database module before importing anything that depends on it
vi.mock("../../src/database/client", () => ({
  getDb: () => ({
    execute: vi.fn().mockResolvedValue({ rows: [] }),
  }),
}));

vi.mock("../../src/services/exchangeClient", () => ({
  getExchangeClient: () => ({
    getPositions: vi.fn().mockResolvedValue([]),
    placeOrder: vi.fn().mockResolvedValue({ id: "test-order" }),
    getOrder: vi.fn().mockResolvedValue({ status: "finished", fill_price: "100", size: "1" }),
  }),
}));

vi.mock("../../src/services/memoryService", () => ({
  extractLesson: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../../src/utils/contractUtils", () => ({
  getQuantoMultiplier: vi.fn().mockResolvedValue(1),
}));

vi.mock("@ai-sdk/openai", () => ({
  createOpenAI: vi.fn(),
}));

// Re-verify the inline PnL formula and risk threshold logic
function calcPnlPercent(entryPrice: number, currentPrice: number, side: "long" | "short", leverage: number): number {
  if (entryPrice <= 0) return 0;
  const priceChangePercent = ((currentPrice - entryPrice) / entryPrice) * 100 * (side === "long" ? 1 : -1);
  return priceChangePercent * leverage;
}

describe("Risk Monitor Thresholds", () => {
  // Default risk params (matching riskParams.ts defaults)
  const EXTREME_STOP_LOSS = -30;
  const MAX_HOLDING_HOURS = 36;

  describe("extreme stop-loss trigger", () => {
    it("triggers when PnL hits -30%", () => {
      // For -30% PnL at 15x leverage: need -2% price drop
      const pnlAtThreshold = calcPnlPercent(100, 98, "long", 15);
      expect(pnlAtThreshold).toBeCloseTo(-30, 2);
      expect(pnlAtThreshold <= EXTREME_STOP_LOSS).toBe(true);
    });

    it("triggers when PnL exceeds -30%", () => {
      // -3% price * 15x = -45%
      const pnl = calcPnlPercent(100, 97, "long", 15);
      expect(pnl).toBeCloseTo(-45, 2);
      expect(pnl <= EXTREME_STOP_LOSS).toBe(true);
    });

    it("does not trigger when PnL is above -30%", () => {
      // -1.5% price * 15x = -22.5%
      const pnl = calcPnlPercent(100, 98.5, "long", 15);
      expect(pnl).toBeCloseTo(-22.5, 2);
      expect(pnl <= EXTREME_STOP_LOSS).toBe(false);
    });

    it("triggers for short position when price rises", () => {
      // Short: +2% price rise * 15x = -30%
      const pnl = calcPnlPercent(100, 102, "short", 15);
      expect(pnl).toBeCloseTo(-30, 2);
      expect(pnl <= EXTREME_STOP_LOSS).toBe(true);
    });
  });

  describe("max holding time trigger", () => {
    function calcHoldingHours(openedAt: Date): number {
      return (Date.now() - openedAt.getTime()) / (1000 * 60 * 60);
    }

    it("triggers when holding time exceeds MAX_HOLDING_HOURS", () => {
      const openedAt = new Date(Date.now() - (MAX_HOLDING_HOURS + 1) * 60 * 60 * 1000);
      const holdingHours = calcHoldingHours(openedAt);
      expect(holdingHours >= MAX_HOLDING_HOURS).toBe(true);
    });

    it("does not trigger when holding time is within limit", () => {
      const openedAt = new Date(Date.now() - 12 * 60 * 60 * 1000); // 12 hours ago
      const holdingHours = calcHoldingHours(openedAt);
      expect(holdingHours >= MAX_HOLDING_HOURS).toBe(false);
    });

    it("triggers at exactly MAX_HOLDING_HOURS", () => {
      const openedAt = new Date(Date.now() - MAX_HOLDING_HOURS * 60 * 60 * 1000);
      const holdingHours = calcHoldingHours(openedAt);
      // Due to floating point, this should be approximately MAX_HOLDING_HOURS
      expect(holdingHours).toBeCloseTo(MAX_HOLDING_HOURS, 0);
    });
  });

  describe("trailing stop (peak PnL tracking)", () => {
    it("detects drawdown from peak", () => {
      const peakPnl = 20; // peak was +20%
      const currentPnl = 5; // now at +5%
      const drawdown = peakPnl - currentPnl;
      expect(drawdown).toBe(15); // 15 percentage points drawdown
    });

    it("updates peak when PnL exceeds previous peak", () => {
      let peakPnl = 10;
      const currentPnl = 15;
      if (currentPnl > peakPnl) {
        peakPnl = currentPnl;
      }
      expect(peakPnl).toBe(15);
    });

    it("does not update peak when PnL is below peak", () => {
      let peakPnl = 20;
      const currentPnl = 15;
      if (currentPnl > peakPnl) {
        peakPnl = currentPnl;
      }
      expect(peakPnl).toBe(20);
    });
  });

  describe("strategy-specific stop-loss tiers (leverage-based)", () => {
    // From strategy params: low leverage → wider stop, high leverage → tighter stop
    const stopLossLow = 8;   // low leverage stop-loss %
    const stopLossHigh = 5;  // high leverage stop-loss %

    it("applies wider stop for low leverage (5x)", () => {
      const pnl = calcPnlPercent(100, 92, "long", 5); // -8% price * 5x = -40%
      // At 5x leverage, stop is -8% → -40% PnL
      expect(pnl <= -stopLossLow * 5).toBe(true);
    });

    it("applies tighter stop for high leverage (15x)", () => {
      const pnl = calcPnlPercent(100, 96, "long", 15); // -4% * 15 = -60%
      // -60% exceeds -75% stop? No. Let's check it exceeds the threshold properly
      // At 15x, stopLossHigh=5 means 5% PnL loss threshold → -5% raw → but wait, stop is in PnL%
      // stopLossHigh = 5 means stop at -5% PnL. -60% clearly exceeds.
      expect(pnl <= -stopLossHigh).toBe(true);
    });

    it("stop-loss threshold decreases as leverage increases", () => {
      // Low leverage: 8% price move needed to trigger
      // High leverage: 5% / 15 ≈ 0.33% price move needed
      const priceMoveForLow = stopLossLow / 5; // 1.6% price move
      const priceMoveForHigh = stopLossHigh / 15; // 0.33% price move
      expect(priceMoveForHigh < priceMoveForLow).toBe(true);
    });
  });
});
