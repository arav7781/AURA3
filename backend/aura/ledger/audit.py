"""Ledger invariants. ``uv run python -m aura.ledger.audit`` exits non-zero on any violation.

I1  every transaction sums to zero
I2  the sum of all balances is zero (issuance holds minus the total supply)
I3  no account other than issuance is negative
I4  every cached balance equals the sum of its entries
I13 no plan period grants more than the top plan's monthly amount; one welcome grant per investor
Further DAO invariants (locks, escrow, releases) register themselves via ``CHECKS`` when those tables exist.
"""

import sys
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from aura.plans import PLANS, ac_to_minor

Check = Callable[[Session], list[str]]
CHECKS: list[tuple[str, Check]] = []


def check(name: str) -> Callable[[Check], Check]:
    def register(fn: Check) -> Check:
        CHECKS.append((name, fn))
        return fn

    return register


@check("I1 transactions balance")
def _tx_sums(s: Session) -> list[str]:
    rows = s.execute(
        text("SELECT tx_id, SUM(amount_minor) FROM ledger_entries GROUP BY tx_id HAVING SUM(amount_minor) <> 0")
    ).all()
    return [f"tx {tx} sums to {total}" for tx, total in rows]


@check("I2 supply is conserved")
def _zero_sum(s: Session) -> list[str]:
    total = s.execute(text("SELECT COALESCE(SUM(balance_minor), 0) FROM ledger_accounts")).scalar()
    return [] if total == 0 else [f"balances sum to {total}, expected 0"]


@check("I3 no negative balances")
def _no_negative(s: Session) -> list[str]:
    rows = s.execute(
        text("SELECT code, balance_minor FROM ledger_accounts WHERE kind <> 'issuance' AND balance_minor < 0")
    ).all()
    return [f"{code} is negative ({bal})" for code, bal in rows]


@check("I4 cached balances match entries")
def _cache_matches(s: Session) -> list[str]:
    rows = s.execute(
        text(
            "SELECT a.code, a.balance_minor, COALESCE(SUM(e.amount_minor), 0) AS derived "
            "FROM ledger_accounts a LEFT JOIN ledger_entries e ON e.account_id = a.id "
            "GROUP BY a.id HAVING a.balance_minor <> derived"
        )
    ).all()
    return [f"{code}: cached {cached} vs entries {derived}" for code, cached, derived in rows]


@check("I13 grants within plan limits")
def _grant_limits(s: Session) -> list[str]:
    cap = ac_to_minor(max(plan.monthly_ac for plan in PLANS.values()))
    problems = [
        f"user {user} period {period} granted {granted} > {cap}"
        for user, period, granted in s.execute(
            text("SELECT user_id, period_index, granted_minor FROM plan_periods WHERE granted_minor > :cap"),
            {"cap": cap},
        ).all()
    ]
    welcome = s.execute(
        text(
            "SELECT e.account_id, COUNT(*) FROM ledger_txs t JOIN ledger_entries e ON e.tx_id = t.id "
            "WHERE t.kind = 'welcome_grant' AND e.amount_minor > 0 GROUP BY e.account_id HAVING COUNT(*) > 1"
        )
    ).all()
    problems += [f"account {account} received {n} welcome grants" for account, n in welcome]
    return problems


def run_audit(s: Session) -> dict[str, list[str]]:
    return {name: fn(s) for name, fn in CHECKS}


def main() -> int:
    from aura.core.db import read_session

    with read_session() as s:
        results = run_audit(s)
    failed = 0
    for name, problems in results.items():
        status = "ok" if not problems else f"FAIL ({len(problems)})"
        print(f"{name:40} {status}")
        for problem in problems[:10]:
            print(f"    {problem}")
        failed += bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
