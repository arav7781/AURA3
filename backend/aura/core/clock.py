"""The application clock.

Everything time-dependent (sessions, plan periods, voting windows) reads ``now()``. In demo mode an
admin can fast-forward the clock (an offset persisted in ``app_state``); tests can freeze it.
"""

import threading
from datetime import UTC, datetime, timedelta

_lock = threading.Lock()
_offset = timedelta(0)
_frozen: datetime | None = None


def now() -> datetime:
    with _lock:
        if _frozen is not None:
            return _frozen
        return datetime.now(UTC) + _offset


def set_offset(offset: timedelta) -> None:
    global _offset
    with _lock:
        _offset = offset


def offset() -> timedelta:
    with _lock:
        return _offset


def freeze(at: datetime) -> None:
    global _frozen
    with _lock:
        _frozen = at.astimezone(UTC)


def advance(delta: timedelta) -> None:
    """Move a frozen clock forward, or add to the offset of a running one."""
    global _frozen, _offset
    with _lock:
        if _frozen is not None:
            _frozen = _frozen + delta
        else:
            _offset = _offset + delta


def unfreeze() -> None:
    global _frozen
    with _lock:
        _frozen = None


def iso(dt: datetime) -> str:
    """Fixed-width UTC ISO-8601 (sorts correctly as text)."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
