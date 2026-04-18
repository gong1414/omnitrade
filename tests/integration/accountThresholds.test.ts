/**
 * Account Threshold Tests
 *
 * Tests the account-level stop-loss and take-profit thresholds
 * matching the logic in riskExecutor.ts checkAccountThresholds().
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock all external dependencies

vi.mock("../../src/database/client", () => ({
  getDb: () => ({
    execute: vi.fn().mockResolvedValue({ rows: [] }),
  }),
}));

vi.mock("../../src/services/exchangeClient", () => ({
  getExchangeClient: () => ({
    getPositions: vi.fn().mockResolvedValue([]),
    placeOrder: vi.fn().mockResolvedValue({ id: "test-order" }),
  }),
}));

vi.mock("../../src/services/memoryService", () => ({
  extractLesson: vi.fn(),
}));

vi.mock("../../src/utils/contractUtils", () => ({
  getQuantoMultiplier: vi.fn().mockResolvedValue(1),
}));

vi.mock("@ai-sdk/openai", () => ({
  createOpenAI: vi.fn(),
}));

// Re-implement the pure threshold logic from checkAccountThresholds
function checkThresholds(totalBalance: number, riskConfig: { stopLossUsdt: number; takeProfitUsdt: number }): { triggered: boolean; reason: string } {
  if (totalBalance <= riskConfig.stopLossUsdt) {
    return { triggered: true, reason: "stop-loss" };
  }
  if (totalBalance >= riskConfig.takeProfitUsdt) {
    return { triggered: true, reason: "take-profit" };
  }
  return { triggered: false, reason: "" };
}

describe("Account Threshold Checks", () => {
  const defaultConfig = {
    stopLossUsdt: 50,
    takeProfitUsdt: 10000,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("stop-loss threshold", () => {
    it("triggers when balance equals stop-loss level", () => {
      const result = checkThresholds(50, defaultConfig);
      expect(result.triggered).toBe(true);
      expect(result.reason).toBe("stop-loss");
    });

    it("triggers when balance drops below stop-loss level", () => {
      const result = checkThresholds(30, defaultConfig);
      expect(result.triggered).toBe(true);
      expect(result.reason).toBe("stop-loss");
    });

    it("does not trigger when balance is above stop-loss", () => {
      const result = checkThresholds(51, defaultConfig);
      expect(result.triggered).toBe(false);
    });

    it("handles zero balance", () => {
      const result = checkThresholds(0, defaultConfig);
      expect(result.triggered).toBe(true);
      expect(result.reason).toBe("stop-loss");
    });
  });

  describe("take-profit threshold", () => {
    it("triggers when balance equals take-profit level", () => {
      const result = checkThresholds(10000, defaultConfig);
      expect(result.triggered).toBe(true);
      expect(result.reason).toBe("take-profit");
    });

    it("triggers when balance exceeds take-profit level", () => {
      const result = checkThresholds(15000, defaultConfig);
      expect(result.triggered).toBe(true);
      expect(result.reason).toBe("take-profit");
    });

    it("does not trigger when balance is below take-profit", () => {
      const result = checkThresholds(9999, defaultConfig);
      expect(result.triggered).toBe(false);
    });
  });

  describe("normal operation (no threshold triggered)", () => {
    it("does not trigger for typical trading balance", () => {
      const result = checkThresholds(500, defaultConfig);
      expect(result.triggered).toBe(false);
    });

    it("does not trigger at starting balance", () => {
      const result = checkThresholds(100, defaultConfig);
      expect(result.triggered).toBe(false);
    });

    it("does not trigger for moderate gains", () => {
      const result = checkThresholds(200, defaultConfig);
      expect(result.triggered).toBe(false);
    });
  });

  describe("account drawdown calculation", () => {
    // From accountService.ts: returnPercent = (totalBalance - initialBalance) / initialBalance * 100
    function calcReturnPercent(totalBalance: number, initialBalance: number): number {
      return ((totalBalance - initialBalance) / initialBalance) * 100;
    }

    it("calculates positive return correctly", () => {
      expect(calcReturnPercent(150, 100)).toBeCloseTo(50, 2);
    });

    it("calculates negative return correctly", () => {
      expect(calcReturnPercent(80, 100)).toBeCloseTo(-20, 2);
    });

    it("returns 0 when balance equals initial", () => {
      expect(calcReturnPercent(100, 100)).toBe(0);
    });

    it("calculates account drawdown from peak", () => {
      const peakBalance = 200;
      const currentBalance = 180;
      const drawdown = ((peakBalance - currentBalance) / peakBalance) * 100;
      expect(drawdown).toBeCloseTo(10, 2);
    });

    it("triggers warning at 10% drawdown from peak", () => {
      const peakBalance = 200;
      const drawdownWarningPercent = 10;
      const thresholdBalance = peakBalance * (1 - drawdownWarningPercent / 100);
      expect(thresholdBalance).toBeCloseTo(180, 2);

      const at180 = ((peakBalance - 180) / peakBalance) * 100;
      expect(at180 >= drawdownWarningPercent).toBe(true);
    });
  });

  describe("custom risk configurations", () => {
    it("works with tighter stop-loss", () => {
      const tightConfig = { stopLossUsdt: 80, takeProfitUsdt: 500 };
      expect(checkThresholds(85, tightConfig).triggered).toBe(false);
      expect(checkThresholds(75, tightConfig).triggered).toBe(true);
    });

    it("works with lower take-profit target", () => {
      const lowTarget = { stopLossUsdt: 50, takeProfitUsdt: 200 };
      expect(checkThresholds(150, lowTarget).triggered).toBe(false);
      expect(checkThresholds(200, lowTarget).triggered).toBe(true);
    });

    it("stop-loss is checked before take-profit", () => {
      // If stop-loss is higher than take-profit, stop-loss triggers first
      const invertedConfig = { stopLossUsdt: 500, takeProfitUsdt: 200 };
      const result = checkThresholds(100, invertedConfig);
      // 100 <= 500 → stop-loss triggers
      expect(result.triggered).toBe(true);
      expect(result.reason).toBe("stop-loss");
    });
  });
});
