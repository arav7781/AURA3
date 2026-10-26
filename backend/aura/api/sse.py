"""Server-sent events over StreamingResponse.

Headers matter: the browser reaches this service through the Next.js rewrite, which gzips responses and
buffers them unless told not to. ``Cache-Control: no-transform`` and ``X-Accel-Buffering: no`` keep events
flowing; a comment heartbeat every 10 s keeps idle proxies from closing the connection.
"""

import json
from collections.abc import AsyncIterator

from fastapi import Request
from fastapi.responses import StreamingResponse

from aura.core.events import Event, bus

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def format_event(event: Event, envelope: dict | None = None) -> str:
    payload = {"seq": event.seq, "ts": event.ts, **(envelope or {}), "data": event.data}
    return f"id: {event.seq}\nevent: {event.type}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def last_event_id(request: Request) -> int:
    raw = request.headers.get("last-event-id") or request.query_params.get("after") or "0"
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def event_stream(request: Request, key: str, envelope: dict | None = None) -> StreamingResponse:
    after = last_event_id(request)

    async def generate() -> AsyncIterator[str]:
        yield "retry: 3000\n\n"
        async for event in bus.subscribe(key, after):
            if await request.is_disconnected():
                return
            yield ": keepalive\n\n" if event is None else format_event(event, envelope)

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)
