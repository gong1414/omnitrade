import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

export interface FakeSseServer {
  port: number;
  push: (envelope: Record<string, unknown>) => void;
  close: () => Promise<void>;
}

/**
 * Tiny `/sse/stream` stand-in that speaks the dashboard envelope contract
 * `{type, payload, trace_id, ts}`. Mirrors the legacy `fake-ws-server.ts`
 * push API — `push(envelope)` immediately broadcasts to every connected
 * `EventSource` client. The HTTP server only needs the stdlib.
 */
export function startFakeSseServer(port = 8765): Promise<FakeSseServer> {
  const clients = new Set<ServerResponse>();

  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    if (req.url !== "/sse/stream" || req.method !== "GET") {
      // CORS preflight or unrelated routes — keep the test harness lenient.
      res.statusCode = 404;
      res.end();
      return;
    }

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache, no-transform");
    res.setHeader("Connection", "keep-alive");
    // Allow the EventSource fetch from the Playwright origin.
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.flushHeaders?.();

    res.write(": connected\n\n");
    clients.add(res);
    req.on("close", () => {
      clients.delete(res);
    });
  });

  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, () => {
      const addr = server.address() as AddressInfo;
      resolve({
        port: addr.port,
        push(envelope) {
          const eventType =
            typeof envelope.type === "string" ? envelope.type : "message";
          const body = JSON.stringify(envelope);
          const frame = `event: ${eventType}\ndata: ${body}\n\n`;
          for (const client of clients) {
            client.write(frame);
          }
        },
        async close() {
          for (const client of clients) {
            try {
              client.end();
            } catch {
              /* ignore */
            }
          }
          await new Promise<void>((res) => server.close(() => res()));
        },
      });
    });
  });
}
