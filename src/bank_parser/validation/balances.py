"""Running-balance chain validation (doc section 22.1) -- the single most
useful check, since it catches a mis-parsed amount even when totals still
happen to add up."""

from __future__ import annotations

from decimal import Decimal

from bank_parser.models.transaction import Transaction

DEFAULT_TOLERANCE = Decimal("0.01")


def check_running_balance_chain(
    transactions: list[Transaction], tolerance: Decimal = DEFAULT_TOLERANCE
) -> tuple[int, int, list[str]]:
    """Walks transactions in extraction (document) order, checking that each
    row's printed balance equals the previous printed balance plus this
    row's signed amount. Re-anchors on the printed balance after every row
    that has one, so a single bad link doesn't cascade into failing every
    subsequent check (doc section 22.1)."""
    checks = 0
    passes = 0
    errors: list[str] = []
    prev_balance: Decimal | None = None

    for txn in transactions:
        if prev_balance is not None and txn.amount is not None and txn.balance is not None:
            checks += 1
            expected = prev_balance + txn.amount
            if abs(expected - txn.balance) <= tolerance:
                passes += 1
            else:
                errors.append(
                    f"{txn.transaction_date} '{txn.description[:40]}': "
                    f"expected balance {expected}, statement shows {txn.balance}"
                )

        if txn.balance is not None:
            prev_balance = txn.balance
        elif prev_balance is not None and txn.amount is not None:
            # No printed balance on this row -- carry an estimate forward so
            # the chain can still check the *next* row that does have one.
            prev_balance = prev_balance + txn.amount

    return checks, passes, errors
