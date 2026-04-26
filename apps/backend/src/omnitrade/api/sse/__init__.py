"""Server-Sent Events transport for the dashboard live feed.

Mirrors the WebSocket stream at `api/ws/stream.py` so the frontend can
flip transport (Stage C of the Agno cutover) without backend regression.
Subscribes to the same `EventBus`, emits the same envelope shape — just
over `text/event-stream` instead of a WebSocket frame.
"""

from omnitrade.api.sse.stream import router as sse_router

__all__ = ["sse_router"]
