"""In-process event bus with replay, for live progress over SSE.

Each stream key (``job:{id}``, ``run:{id}``) has a ring buffer of numbered events. Subscribers get
everything after the ``Last-Event-ID`` they already saw, then wait for new events. Publishers may run on
worker threads (OCR, evaluation); waiters are woken on the event loop with ``call_soon_threadsafe``.
Closed streams are kept for an hour so a client reconnecting after completion still gets the tail.
"""

import asyncio
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from aura.core import clock

_BUFFER = 2000
_TTL_S = 3600


@dataclass(frozen=True)
class Event:
    seq: int
    type: str
    data: dict[str, Any]
    ts: str


@dataclass
class _Stream:
    events: deque[Event] = field(default_factory=lambda: deque(maxlen=_BUFFER))
    seq: int = 0
    closed: bool = False
    closed_at: float | None = None
    waiters: set[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]] = field(default_factory=set)


class EventBus:
    def __init__(self) -> None:
        self._streams: dict[str, _Stream] = {}
        self._lock = threading.Lock()

    def _stream(self, key: str) -> _Stream:
        stream = self._streams.get(key)
        if stream is None:
            stream = self._streams[key] = _Stream()
        return stream

    def publish(self, key: str, type: str, data: dict[str, Any] | None = None) -> int:
        with self._lock:
            stream = self._stream(key)
            if stream.closed:
                return stream.seq
            stream.seq += 1
            stream.events.append(Event(stream.seq, type, data or {}, clock.iso(clock.now())))
            waiters, stream.waiters = stream.waiters, set()
            seq = stream.seq
        self._wake(waiters)
        return seq

    def close(self, key: str) -> None:
        with self._lock:
            stream = self._stream(key)
            stream.closed = True
            stream.closed_at = time.monotonic()
            waiters, stream.waiters = stream.waiters, set()
        self._wake(waiters)
        self._expire()

    def last_seq(self, key: str) -> int:
        with self._lock:
            stream = self._streams.get(key)
            return stream.seq if stream else 0

    @staticmethod
    def _wake(waiters: set[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]]) -> None:
        for loop, future in waiters:
            if not loop.is_closed():
                loop.call_soon_threadsafe(lambda f=future: None if f.done() else f.set_result(None))

    def _expire(self) -> None:
        now = time.monotonic()
        with self._lock:
            for key in [k for k, s in self._streams.items() if s.closed and s.closed_at and now - s.closed_at > _TTL_S]:
                del self._streams[key]

    async def subscribe(self, key: str, after_seq: int = 0, *, heartbeat_s: float = 10.0) -> AsyncIterator[Event | None]:
        """Yield events with seq > ``after_seq``; yields ``None`` as a heartbeat when idle for ``heartbeat_s``.
        Ends once the stream is closed and drained."""
        loop = asyncio.get_running_loop()
        last = after_seq
        while True:
            with self._lock:
                stream = self._stream(key)
                pending = [e for e in stream.events if e.seq > last]
                finished = stream.closed
                future: asyncio.Future[None] | None = None
                if not pending and not finished:
                    future = loop.create_future()
                    stream.waiters.add((loop, future))
            for event in pending:
                last = event.seq
                yield event
            if pending:
                continue
            if finished:
                return
            assert future is not None
            try:
                await asyncio.wait_for(future, timeout=heartbeat_s)
            except TimeoutError:
                with self._lock:
                    self._stream(key).waiters.discard((loop, future))
                yield None


bus = EventBus()
