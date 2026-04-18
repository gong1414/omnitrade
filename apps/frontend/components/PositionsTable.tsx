"use client";

import { useState } from "react";
import { usePositions } from "@/hooks/usePositions";
import { apiClient } from "@/lib/api/client";
import { cn, fmtNum, fmtPercent } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Dialog, DialogFooter } from "./ui/dialog";
import { Input } from "./ui/input";
import type { Position } from "@/lib/api/types";
import { ApiError } from "@/lib/api/client";

export function PositionsTable() {
  const { positions, isLoading, mutate } = usePositions();
  const [target, setTarget] = useState<Position | null>(null);
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onClose() {
    if (!target) return;
    setSubmitting(true);
    setErr(null);
    try {
      await apiClient.closePosition({ symbol: target.symbol, password });
      await mutate();
      setTarget(null);
      setPassword("");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Failed to close position";
      setErr(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card data-testid="positions-card">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Open Positions</CardTitle>
        <span className="text-xs text-neutral-500">{positions.length}</span>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading && positions.length === 0 ? (
          <div className="p-4 text-sm text-neutral-500">Loading…</div>
        ) : positions.length === 0 ? (
          <div className="p-4 text-sm text-neutral-500">No open positions.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-neutral-800 text-neutral-500">
                  <th className="px-3 py-2 text-left">Symbol</th>
                  <th className="px-3 py-2 text-left">Side</th>
                  <th className="px-3 py-2 text-right">Qty</th>
                  <th className="px-3 py-2 text-right">Entry</th>
                  <th className="px-3 py-2 text-right">Current</th>
                  <th className="px-3 py-2 text-right">PnL</th>
                  <th className="px-3 py-2 text-right">Lev</th>
                  <th className="px-3 py-2 text-right">Closed%</th>
                  <th className="px-3 py-2 text-right">Peak%</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => {
                  const pnl = Number(p.unrealized_pnl);
                  return (
                    <tr
                      key={p.id}
                      data-testid="position-row"
                      className="border-b border-neutral-900 last:border-b-0"
                    >
                      <td className="px-3 py-2 font-medium text-neutral-200">{p.symbol}</td>
                      <td className="px-3 py-2">
                        <span
                          className={cn(
                            "inline-block rounded px-1.5 py-0.5 text-[10px] uppercase",
                            p.side === "long"
                              ? "bg-emerald-950 text-emerald-300"
                              : "bg-red-950 text-red-300",
                          )}
                        >
                          {p.side}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right text-neutral-300">
                        {fmtNum(p.quantity, 4)}
                      </td>
                      <td className="px-3 py-2 text-right text-neutral-300">
                        {fmtNum(p.entry_price, 4)}
                      </td>
                      <td className="px-3 py-2 text-right text-neutral-300">
                        {fmtNum(p.current_price, 4)}
                      </td>
                      <td
                        className={cn(
                          "px-3 py-2 text-right tabular-nums",
                          pnl >= 0 ? "text-emerald-400" : "text-red-400",
                        )}
                      >
                        {fmtNum(p.unrealized_pnl, 2)}
                      </td>
                      <td className="px-3 py-2 text-right text-neutral-300">{p.leverage}x</td>
                      <td className="px-3 py-2 text-right text-neutral-400">
                        {fmtNum(p.cumulative_close_pct, 0)}%
                      </td>
                      <td className="px-3 py-2 text-right text-neutral-400">
                        {fmtPercent(p.trailing_peak_pnl_pct, 2)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => setTarget(p)}
                          data-testid="close-button"
                        >
                          Close
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      <Dialog
        open={target !== null}
        onOpenChange={(o) => {
          if (!o) {
            setTarget(null);
            setPassword("");
            setErr(null);
          }
        }}
        title={target ? `Close ${target.symbol}?` : undefined}
      >
        <p className="text-sm text-neutral-400">
          This submits a market close for the full remaining quantity. Password required.
        </p>
        <div className="mt-4 space-y-2">
          <Input
            type="password"
            placeholder="manual-close password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            data-testid="close-password"
          />
          {err ? <p className="text-xs text-red-400">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => setTarget(null)} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={onClose}
            disabled={submitting || password.length === 0}
            data-testid="close-submit"
          >
            {submitting ? "Closing…" : "Close position"}
          </Button>
        </DialogFooter>
      </Dialog>
    </Card>
  );
}
