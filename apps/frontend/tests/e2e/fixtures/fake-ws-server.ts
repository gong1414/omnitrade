import { WebSocketServer, type WebSocket } from "ws";

export interface FakeWsServer {
  port: number;
  sockets: Set<WebSocket>;
  push: (envelope: Record<string, unknown>) => void;
  close: () => Promise<void>;
}

/**
 * Tiny `/ws/stream` stand-in that speaks the Phase 5 envelope contract:
 * `{type, payload, trace_id, ts}`. Also replies to "ping" with "pong".
 */
export function startFakeWsServer(port = 8765): Promise<FakeWsServer> {
  return new Promise((resolve, reject) => {
    const wss = new WebSocketServer({ port, path: "/ws/stream" });
    const sockets = new Set<WebSocket>();

    wss.on("connection", (sock: WebSocket) => {
      sockets.add(sock);
      sock.on("message", (data) => {
        const text = data.toString();
        if (text === "ping") sock.send("pong");
      });
      sock.on("close", () => sockets.delete(sock));
    });

    wss.on("listening", () => {
      const addr = wss.address();
      if (addr && typeof addr === "object") {
        resolve({
          port: addr.port,
          sockets,
          push(envelope) {
            const msg = JSON.stringify(envelope);
            for (const s of sockets) {
              if (s.readyState === s.OPEN) s.send(msg);
            }
          },
          async close() {
            await new Promise<void>((res) => {
              for (const s of sockets) s.terminate();
              wss.close(() => res());
            });
          },
        });
      }
    });

    wss.on("error", reject);
  });
}
