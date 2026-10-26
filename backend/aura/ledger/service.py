"""Posting AuraCoin transactions.

Every movement is one transaction of two or more legs that sum to zero. ``post_tx`` must run inside
``write_tx()`` (``BEGIN IMMEDIATE``), so concurrent writers are serialised. Overdrafts are refused by a
guarded UPDATE (and a CHECK constraint behind it); entries are append-only (database triggers).

Idempotency: every transaction carries a key. Posting the same key with the same legs returns the existing
transaction; the same key with different legs is a conflict.

Accounts: ``sys:issuance`` (the only account allowed below zero; minus total supply), ``sys:fees``,
``user:{u}:wallet``, ``user:{u}:locked`` (vote locks), ``startup:{s}:wallet``, ``proposal:{p}:escrow``.
"""

import hashlib
import json
from collections.abc import Sequence

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from aura.core.errors import Conflict, InsufficientFunds
from aura.models import LedgerAccount, LedgerEntry, LedgerTx
from aura.plans import MINOR_PER_AC


class IdempotencyConflict(Conflict):
    code = "IDEMPOTENCY_CONFLICT"


def _get_or_create(
    s: Session,
    code: str,
    kind: str,
    *,
    owner_user_id: str | None = None,
    owner_startup_id: str | None = None,
    proposal_id: str | None = None,
) -> LedgerAccount:
    account = s.scalar(select(LedgerAccount).where(LedgerAccount.code == code))
    if account is None:
        account = LedgerAccount(
            code=code,
            kind=kind,
            owner_user_id=owner_user_id,
            owner_startup_id=owner_startup_id,
            proposal_id=proposal_id,
            balance_minor=0,
        )
        s.add(account)
        s.flush()
    return account


def issuance(s: Session) -> LedgerAccount:
    return _get_or_create(s, "sys:issuance", "issuance")


def fees(s: Session) -> LedgerAccount:
    return _get_or_create(s, "sys:fees", "fees")


def wallet(s: Session, user_id: str) -> LedgerAccount:
    return _get_or_create(s, f"user:{user_id}:wallet", "wallet", owner_user_id=user_id)


def locked(s: Session, user_id: str) -> LedgerAccount:
    return _get_or_create(s, f"user:{user_id}:locked", "locked", owner_user_id=user_id)


def startup_wallet(s: Session, startup_id: str) -> LedgerAccount:
    return _get_or_create(s, f"startup:{startup_id}:wallet", "startup", owner_startup_id=startup_id)


def escrow(s: Session, proposal_id: str) -> LedgerAccount:
    return _get_or_create(s, f"proposal:{proposal_id}:escrow", "escrow", proposal_id=proposal_id)


Leg = tuple[LedgerAccount | int, int]


def post_tx(
    s: Session,
    *,
    kind: str,
    key: str,
    legs: Sequence[Leg],
    actor_user_id: str | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    memo: str | None = None,
) -> tuple[LedgerTx, bool]:
    """Post a balanced transaction. Returns ``(tx, created)``; ``created`` is False on an idempotent replay."""
    merged: dict[int, int] = {}
    for account, amount in legs:
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise TypeError("ledger amounts are integer minor units")
        account_id = account.id if isinstance(account, LedgerAccount) else int(account)
        merged[account_id] = merged.get(account_id, 0) + amount
    items = sorted((aid, amt) for aid, amt in merged.items() if amt != 0)
    if len(items) < 2:
        raise ValueError("a transaction needs at least two non-zero legs")
    if sum(amt for _, amt in items) != 0:
        raise ValueError("transaction legs must sum to zero")
    legs_hash = hashlib.sha256(json.dumps(items).encode()).hexdigest()

    existing = s.scalar(select(LedgerTx).where(LedgerTx.idempotency_key == key))
    if existing is not None:
        if existing.legs_hash == legs_hash:
            return existing, False
        raise IdempotencyConflict("This idempotency key was already used for a different transaction", key=key)

    # Debits first, so an overdraft fails before any credit is applied (the transaction rolls back anyway).
    for account_id, amount in sorted(items, key=lambda item: item[1]):
        result = s.execute(
            text(
                "UPDATE ledger_accounts SET balance_minor = balance_minor + :amount "
                "WHERE id = :id AND (kind = 'issuance' OR balance_minor + :amount >= 0)"
            ),
            {"amount": amount, "id": account_id},
        )
        if result.rowcount != 1:
            account = s.get(LedgerAccount, account_id)
            s.expire_all()
            raise InsufficientFunds(
                "Not enough AuraCoin",
                account=account.code if account else account_id,
                needed_minor=-amount,
                available_minor=account.balance_minor if account else None,
            )

    tx = LedgerTx(
        kind=kind,
        idempotency_key=key,
        legs_hash=legs_hash,
        actor_user_id=actor_user_id,
        ref_type=ref_type,
        ref_id=ref_id,
        memo=memo,
    )
    s.add(tx)
    s.flush()
    s.add_all([LedgerEntry(tx_id=tx.id, account_id=aid, amount_minor=amt) for aid, amt in items])
    s.flush()
    s.expire_all()  # cached balances on loaded accounts are stale after the raw UPDATEs
    return tx, True


def transfer(
    s: Session, *, kind: str, key: str, source: LedgerAccount, dest: LedgerAccount, amount_minor: int, **refs: str | None
) -> tuple[LedgerTx, bool]:
    if amount_minor <= 0:
        raise ValueError("transfer amount must be positive")
    return post_tx(s, kind=kind, key=key, legs=[(source, -amount_minor), (dest, amount_minor)], **refs)


def balance(s: Session, account: LedgerAccount) -> int:
    return int(s.scalar(select(LedgerAccount.balance_minor).where(LedgerAccount.id == account.id)) or 0)


def user_balances(s: Session, user_id: str) -> dict[str, int]:
    """Available, locked (votes) and escrowed (pledges) AuraCoin for a user, in minor units."""
    codes = {f"user:{user_id}:wallet": "available", f"user:{user_id}:locked": "locked"}
    rows = s.execute(
        select(LedgerAccount.code, LedgerAccount.balance_minor).where(LedgerAccount.code.in_(codes))
    ).all()
    out = {"available": 0, "locked": 0, "escrowed": 0}
    for code, value in rows:
        out[codes[code]] = int(value)
    out["escrowed"] = _escrowed_for_user(s, user_id)
    return out


def _escrowed_for_user(s: Session, user_id: str) -> int:
    # Pledges arrive with the DAO tables; until then nothing is escrowed per user.
    table_exists = s.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pledges'")).first()
    if not table_exists:
        return 0
    value = s.execute(
        text(
            "SELECT COALESCE(SUM(amount_minor - released_minor - refunded_minor), 0) FROM pledges "
            "WHERE investor_id = :u"
        ),
        {"u": user_id},
    ).scalar()
    return int(value or 0)


def format_ac(amount_minor: int) -> str:
    whole, frac = divmod(abs(amount_minor), MINOR_PER_AC)
    sign = "-" if amount_minor < 0 else ""
    return f"{sign}{whole:,}" + (f".{frac:02d}" if frac else "") + " AC"
