/**
 * Browser-scoped singleton WS client. SSR calls return a no-op object.
 */

import { createWsClient, type WsClient } from "./client";

let instance: WsClient | null = null;

export function getWsClient(): WsClient | null {
  if (typeof window === "undefined") return null;
  if (!instance) {
    instance = createWsClient();
    instance.connect();
  }
  return instance;
}

/** Reset used by tests. */
export function __resetWsClient() {
  if (instance) {
    try {
      instance.disconnect();
    } catch {
      /* ignore */
    }
  }
  instance = null;
}
