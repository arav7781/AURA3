"""Property test: random sequences of grants, transfers, locks and unlocks keep every ledger invariant and
match a plain-Python reference model of the balances."""

import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aura.core.db import read_session, write_tx
from aura.core.errors import InsufficientFunds
from aura.ledger import service as ledger
from aura.ledger.audit import run_audit
from aura.models import User

N_USERS = 3
op = st.one_of(
    st.tuples(st.just("grant"), st.integers(0, N_USERS - 1), st.integers(1, 10_000)),
    st.tuples(st.just("transfer"), st.integers(0, N_USERS - 1), st.integers(0, N_USERS - 1), st.integers(1, 10_000)),
    st.tuples(st.just("lock"), st.integers(0, N_USERS - 1), st.integers(1, 10_000)),
    st.tuples(st.just("unlock"), st.integers(0, N_USERS - 1), st.integers(1, 10_000)),
)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(ops=st.lists(op, max_size=25))
def test_random_operations_keep_invariants(app_env, ops):
    with write_tx() as s:
        users = []
        for _ in range(N_USERS):
            user = User(email=f"{uuid.uuid4().hex}@x.io", password_hash="x", role="investor", name="P")
            s.add(user)
            s.flush()
            users.append(user.id)
    model = {("wallet", u): 0 for u in users} | {("locked", u): 0 for u in users}

    for step, operation in enumerate(ops):
        key = f"{uuid.uuid4().hex}:{step}"
        kind = operation[0]
        try:
            with write_tx() as s:
                if kind == "grant":
                    _, i, amt = operation
                    ledger.post_tx(s, kind="g", key=key, legs=[(ledger.issuance(s), -amt), (ledger.wallet(s, users[i]), amt)])
                    model[("wallet", users[i])] += amt
                elif kind == "transfer":
                    _, i, j, amt = operation
                    if i == j:
                        continue
                    ledger.transfer(s, kind="t", key=key, source=ledger.wallet(s, users[i]),
                                    dest=ledger.wallet(s, users[j]), amount_minor=amt)
                    model[("wallet", users[i])] -= amt
                    model[("wallet", users[j])] += amt
                elif kind == "lock":
                    _, i, amt = operation
                    ledger.transfer(s, kind="l", key=key, source=ledger.wallet(s, users[i]),
                                    dest=ledger.locked(s, users[i]), amount_minor=amt)
                    model[("wallet", users[i])] -= amt
                    model[("locked", users[i])] += amt
                else:
                    _, i, amt = operation
                    ledger.transfer(s, kind="u", key=key, source=ledger.locked(s, users[i]),
                                    dest=ledger.wallet(s, users[i]), amount_minor=amt)
                    model[("locked", users[i])] -= amt
                    model[("wallet", users[i])] += amt
        except InsufficientFunds:
            pass  # refused: the model was not updated either (the update lines run only after success)

    with read_session() as s:
        for (kind, user_id), expected in model.items():
            account = ledger.wallet(s, user_id) if kind == "wallet" else ledger.locked(s, user_id)
            assert ledger.balance(s, account) == expected
        assert {name: p for name, p in run_audit(s).items() if p} == {}
