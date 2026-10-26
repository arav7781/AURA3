import threading
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from aura.core.db import read_session, write_tx
from aura.core.errors import InsufficientFunds
from aura.ledger import service as ledger
from aura.ledger.audit import run_audit
from aura.ledger.service import IdempotencyConflict
from aura.models import User

AC = 100


def _user(s, role="investor") -> str:
    user = User(email=f"{uuid.uuid4().hex}@x.io", password_hash="x", role=role, name="T")
    s.add(user)
    s.flush()
    return user.id


def _fund(s, user_id: str, ac: int) -> None:
    ledger.post_tx(
        s,
        kind="test_grant",
        key=f"fund:{user_id}:{uuid.uuid4().hex}",
        legs=[(ledger.issuance(s), -ac * AC), (ledger.wallet(s, user_id), ac * AC)],
    )


def _all_ok(s) -> None:
    problems = {name: p for name, p in run_audit(s).items() if p}
    assert problems == {}


def test_balanced_posting_and_idempotent_replay(app_env):
    with write_tx() as s:
        uid = _user(s)
        tx, created = ledger.post_tx(
            s, kind="g", key="k1", legs=[(ledger.issuance(s), -500 * AC), (ledger.wallet(s, uid), 500 * AC)]
        )
        assert created
        again, created_again = ledger.post_tx(
            s, kind="g", key="k1", legs=[(ledger.issuance(s), -500 * AC), (ledger.wallet(s, uid), 500 * AC)]
        )
        assert not created_again and again.id == tx.id
        assert ledger.balance(s, ledger.wallet(s, uid)) == 500 * AC
        with pytest.raises(IdempotencyConflict):
            ledger.post_tx(
                s, kind="g", key="k1", legs=[(ledger.issuance(s), -1 * AC), (ledger.wallet(s, uid), 1 * AC)]
            )
    with read_session() as s:
        _all_ok(s)


def test_unbalanced_and_degenerate_legs_are_rejected(app_env):
    with write_tx() as s:
        uid = _user(s)
        with pytest.raises(ValueError):
            ledger.post_tx(s, kind="x", key="u1", legs=[(ledger.issuance(s), -5), (ledger.wallet(s, uid), 4)])
        with pytest.raises(ValueError):
            ledger.post_tx(s, kind="x", key="u2", legs=[(ledger.wallet(s, uid), 0), (ledger.fees(s), 0)])
        with pytest.raises(TypeError):
            ledger.post_tx(s, kind="x", key="u3", legs=[(ledger.issuance(s), -1.5), (ledger.wallet(s, uid), 1.5)])


def test_overdraft_is_refused_and_rolled_back(app_env):
    with write_tx() as s:
        uid = _user(s)
        _fund(s, uid, 100)
    with pytest.raises(InsufficientFunds):
        with write_tx() as s:
            ledger.transfer(
                s, kind="t", key="over", source=ledger.wallet(s, uid), dest=ledger.locked(s, uid),
                amount_minor=150 * AC,
            )
    with read_session() as s:
        assert s.execute(text("SELECT balance_minor FROM ledger_accounts WHERE code = :c"),
                         {"c": f"user:{uid}:wallet"}).scalar() == 100 * AC
        assert s.execute(text("SELECT COUNT(*) FROM ledger_txs WHERE idempotency_key = 'over'")).scalar() == 0
        _all_ok(s)


def test_entries_and_transactions_are_append_only(app_env):
    with write_tx() as s:
        uid = _user(s)
        _fund(s, uid, 10)
    for statement in (
        "UPDATE ledger_entries SET amount_minor = 1",
        "DELETE FROM ledger_entries",
        "UPDATE ledger_txs SET memo = 'x'",
        "DELETE FROM ledger_txs",
    ):
        with pytest.raises(DatabaseError, match="append-only"):
            with write_tx() as s:
                s.execute(text(statement))


def test_negative_balance_is_blocked_by_the_schema(app_env):
    with write_tx() as s:
        uid = _user(s)
        _fund(s, uid, 1)
    with pytest.raises(DatabaseError):
        with write_tx() as s:
            s.execute(text("UPDATE ledger_accounts SET balance_minor = -1 WHERE code = :c"), {"c": f"user:{uid}:wallet"})


def test_audit_detects_entries_that_bypass_balances(app_env):
    with write_tx() as s:
        uid = _user(s)
        _fund(s, uid, 10)
        wallet_id = ledger.wallet(s, uid).id
        # A raw insert that skips post_tx: balances no longer match entries and the tx no longer sums to zero.
        s.execute(text("INSERT INTO ledger_txs (kind, idempotency_key, legs_hash, created_at) "
                       "VALUES ('bad', 'bad', 'x', '2026-01-01T00:00:00.000000Z')"))
        tx_id = s.execute(text("SELECT id FROM ledger_txs WHERE idempotency_key = 'bad'")).scalar()
        s.execute(text("INSERT INTO ledger_entries (tx_id, account_id, amount_minor, created_at) "
                       "VALUES (:t, :a, 7, '2026-01-01T00:00:00.000000Z')"), {"t": tx_id, "a": wallet_id})
    with read_session() as s:
        results = run_audit(s)
    assert results["I1 transactions balance"] and results["I4 cached balances match entries"]


def test_concurrent_spends_cannot_overdraw(app_env):
    """16 threads each try to move 1,000 AC out of a 5,000 AC wallet: exactly five succeed."""
    with write_tx() as s:
        uid = _user(s)
        _fund(s, uid, 5000)
    outcomes: list[str] = []
    lock = threading.Lock()
    start = threading.Barrier(16)

    def spend(i: int) -> None:
        start.wait()
        try:
            with write_tx() as s:
                ledger.transfer(
                    s, kind="pledge", key=f"spend:{i}", source=ledger.wallet(s, uid),
                    dest=ledger.escrow(s, f"proposal-{i}"), amount_minor=1000 * AC,
                )
            result = "ok"
        except InsufficientFunds:
            result = "refused"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=spend, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert outcomes.count("ok") == 5 and outcomes.count("refused") == 11
    with read_session() as s:
        assert s.execute(text("SELECT balance_minor FROM ledger_accounts WHERE code = :c"),
                         {"c": f"user:{uid}:wallet"}).scalar() == 0
        _all_ok(s)
