"""SQLite access: one database file, two engines.

- the read/write engine opens every transaction with ``BEGIN IMMEDIATE``, so writers are serialised by
  SQLite itself (no double spends between threads), and
- the read-only engine uses a plain ``BEGIN`` for consistent snapshots under WAL.

The only way to mutate is ``write_tx()``. Endpoints are synchronous and run in FastAPI's threadpool.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from aura.core.config import get_settings

_rw: Engine | None = None
_ro: Engine | None = None
_RW: sessionmaker[Session] | None = None
_RO: sessionmaker[Session] | None = None


def _make_engine(url: str, *, begin: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):  # noqa: ANN001
        dbapi_conn.isolation_level = None  # we emit BEGIN ourselves
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")  # must run outside a transaction
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn):  # noqa: ANN001
        conn.exec_driver_sql(begin)

    return engine


def init_engines(url: str | None = None) -> None:
    """Create (or recreate) the engines. Tests call this with a temporary database URL."""
    global _rw, _ro, _RW, _RO
    dispose_engines()
    url = url or get_settings().database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    _rw = _make_engine(url, begin="BEGIN IMMEDIATE")
    _ro = _make_engine(url, begin="BEGIN")
    _RW = sessionmaker(bind=_rw, expire_on_commit=False)
    _RO = sessionmaker(bind=_ro, expire_on_commit=False)


def dispose_engines() -> None:
    global _rw, _ro, _RW, _RO
    for engine in (_rw, _ro):
        if engine is not None:
            engine.dispose()
    _rw = _ro = None
    _RW = _RO = None


def rw_engine() -> Engine:
    if _rw is None:
        init_engines()
    assert _rw is not None
    return _rw


@contextmanager
def write_tx() -> Iterator[Session]:
    """A serialised read/write transaction; commits on success, rolls back on any exception."""
    if _RW is None:
        init_engines()
    assert _RW is not None
    with _RW.begin() as session:
        yield session


@contextmanager
def read_session() -> Iterator[Session]:
    if _RO is None:
        init_engines()
    assert _RO is not None
    with _RO.begin() as session:
        yield session
