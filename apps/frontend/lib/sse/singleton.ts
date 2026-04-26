/**
 * Browser-scoped singleton SSE client. SSR calls return `null` so the
 * dashboard hook can render its initial markup without a live connection.
 *
 * Mirrors the shape of the legacy `lib/ws/singleton.ts` so the realtime
 * hook can swap one transport for the other in a single import edit.
 */

import { SseClient } from "./client";

let instance: SseClient | null = null;

export function getSseClient(): SseClient | null {
  if (typeof window === "undefined") return null;
  if (!instance) {
    instance = new SseClient();
    instance.connect();
  }
  return instance;
}

/** Reset used by tests. */
export function __resetSseClient(): void {
  if (instance) {
    try {
      instance.disconnect();
    } catch {
      /* ignore */
    }
  }
  instance = null;
}
