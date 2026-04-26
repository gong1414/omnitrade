"use client";

/**
 * T9 — Human-in-the-loop approval banner for above-threshold opens.
 *
 * The trading agent decorates ``record_open_decision`` (registered as
 * ``open_position``) with ``requires_confirmation=True``. When the
 * USD notional of the LLM's open exceeds
 * ``HITL_OPEN_SIZE_THRESHOLD_USD`` the backend publishes
 * ``EVENT_RUN_PAUSED`` over SSE; this banner renders the paused tool
 * args and exposes Approve / Reject buttons that POST to
 * ``/api/v1/runs/{run_id}/{confirm,reject}``. Below the threshold the
 * banner never appears (the wrapper auto-confirms server-side).
 *
 * Style mirrors the existing dashboard banners (ConnectionBanner /
 * orchestrator-error variant) — same border / bg / typography. No new
 * design system.
 */

import { useState } from "react";
import { Badge } from "./ui/badge";
import { apiClient, ApiError } from "@/lib/api/client";
import type { RunPausedPayload } from "@/lib/api/types";

export function ApprovalBanner({
  pausedRun,
  onResolved,
}: {
  pausedRun: RunPausedPayload | null;
  onResolved?: () => void;
}) {
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (pausedRun === null) return null;

  const tool = pausedRun.tool_name;
  const reason = pausedRun.requires_confirmation_reason;
  const args = pausedRun.tool_args ?? {};

  // Friendly summary line — symbol / side / size / leverage / notional.
  // Tolerant of unknown args so a future schema change doesn't blow up
  // the banner.
  const symbol = String(args.symbol ?? "?");
  const side = String(args.side ?? "?");
  const size = args.size != null ? String(args.size) : "?";
  const leverage = args.leverage != null ? String(args.leverage) : "?";
  const entryPrice =
    args.entry_price ?? args.price ?? args.mark_price ?? null;

  const handle = async (decision: "approve" | "reject") => {
    if (busy) return;
    setBusy(decision);
    setError(null);
    try {
      if (decision === "approve") {
        await apiClient.confirmRun(pausedRun.run_id);
      } else {
        await apiClient.rejectRun(pausedRun.run_id);
      }
      onResolved?.();
    } catch (err) {
      // 404 is the duplicate-click / already-resolved case — treat as
      // a soft success so the banner closes.
      if (err instanceof ApiError && err.status === 404) {
        onResolved?.();
        return;
      }
      setError(err instanceof Error ? err.message : "approval failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      className="flex flex-col gap-2 rounded-md border border-amber-700 bg-amber-950/40 px-3 py-2 text-xs text-amber-100"
      data-testid="approval-banner"
      role="alertdialog"
      aria-label="HITL approval required"
    >
      <div className="flex items-center gap-2">
        <Badge tone="warn">approval</Badge>
        <span className="font-medium">
          {tool} pending — {reason}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-amber-200/90 tabular-nums">
        <dt className="opacity-70">symbol</dt>
        <dd>{symbol}</dd>
        <dt className="opacity-70">side</dt>
        <dd>{side}</dd>
        <dt className="opacity-70">size</dt>
        <dd>{size}</dd>
        <dt className="opacity-70">leverage</dt>
        <dd>{leverage}x</dd>
        {entryPrice !== null && (
          <>
            <dt className="opacity-70">entry</dt>
            <dd>{String(entryPrice)}</dd>
          </>
        )}
        <dt className="opacity-70">run_id</dt>
        <dd className="truncate font-mono">{pausedRun.run_id}</dd>
      </dl>

      {error && (
        <div className="text-red-300" role="status">
          {error}
        </div>
      )}

      <div className="flex items-center gap-2 pt-1">
        <button
          type="button"
          onClick={() => handle("approve")}
          disabled={busy !== null}
          className="rounded border border-emerald-600 bg-emerald-900/40 px-2 py-1 text-emerald-100 hover:bg-emerald-900/60 disabled:opacity-50"
          data-testid="approval-banner-approve"
        >
          {busy === "approve" ? "approving…" : "approve"}
        </button>
        <button
          type="button"
          onClick={() => handle("reject")}
          disabled={busy !== null}
          className="rounded border border-red-700 bg-red-950/40 px-2 py-1 text-red-100 hover:bg-red-950/70 disabled:opacity-50"
          data-testid="approval-banner-reject"
        >
          {busy === "reject" ? "rejecting…" : "reject"}
        </button>
      </div>
    </div>
  );
}
