"""Ties the individual checks together into one StatementValidation (doc
section 22.5).

Reconciliation is done by *direction* (debit/charge vs credit/payment)
rather than by raw amount sign, and compared using absolute values: a
debit/checking layout represents "money leaving the account" as a negative
signed amount, while a credit-card layout with a single signed-amount column
mirrors whatever sign the statement itself prints (BBVA prints charges with a
leading "+" and payments with a leading "-"). Comparing magnitudes by
direction sidesteps that difference instead of assuming one convention.
"""

from __future__ import annotations

from decimal import Decimal

from bank_parser.models.transaction import Transaction
from bank_parser.models.validation import StatementValidation
from bank_parser.validation.balances import DEFAULT_TOLERANCE, check_running_balance_chain
from bank_parser.validation.totals import PrintedTotals


def transaction_direction(txn: Transaction) -> str | None:
    if txn.debit is not None:
        return "debit"
    if txn.credit is not None:
        return "credit"
    if txn.amount is not None and txn.amount != 0:
        return "debit" if txn.amount > 0 else "credit"
    return None


def transaction_magnitude(txn: Transaction, direction: str) -> Decimal:
    if direction == "debit":
        return txn.debit if txn.debit is not None else abs(txn.amount)
    return txn.credit if txn.credit is not None else abs(txn.amount)


def validate_statement(
    transactions: list[Transaction],
    totals: PrintedTotals,
    tolerance: Decimal = DEFAULT_TOLERANCE,
) -> StatementValidation:
    checks, passes, chain_errors = check_running_balance_chain(transactions, tolerance)
    warnings: list[str] = list(chain_errors)

    debit_txns = [t for t in transactions if transaction_direction(t) == "debit"]
    credit_txns = [t for t in transactions if transaction_direction(t) == "credit"]
    extracted_debit_sum = sum((transaction_magnitude(t, "debit") for t in debit_txns), Decimal("0"))
    extracted_credit_sum = sum((transaction_magnitude(t, "credit") for t in credit_txns), Decimal("0"))

    debit_reconciled = None
    if totals.debit_total is not None:
        debit_reconciled = abs(extracted_debit_sum - abs(totals.debit_total)) <= tolerance
        if not debit_reconciled:
            warnings.append(
                f"debit total mismatch: extracted {extracted_debit_sum}, "
                f"statement prints {totals.debit_total}"
            )

    credit_reconciled = None
    if totals.credit_total is not None:
        credit_reconciled = abs(extracted_credit_sum - abs(totals.credit_total)) <= tolerance
        if not credit_reconciled:
            warnings.append(
                f"credit total mismatch: extracted {extracted_credit_sum}, "
                f"statement prints {totals.credit_total}"
            )

    movement_count_reconciled = None
    count_results: list[bool] = []
    if totals.debit_count is not None:
        ok = len(debit_txns) == totals.debit_count
        count_results.append(ok)
        if not ok:
            warnings.append(
                f"debit movement count mismatch: extracted {len(debit_txns)}, "
                f"statement prints {totals.debit_count}"
            )
    if totals.credit_count is not None:
        ok = len(credit_txns) == totals.credit_count
        count_results.append(ok)
        if not ok:
            warnings.append(
                f"credit movement count mismatch: extracted {len(credit_txns)}, "
                f"statement prints {totals.credit_count}"
            )
    if count_results:
        movement_count_reconciled = all(count_results)

    return StatementValidation(
        running_balance_checks=checks,
        running_balance_passes=passes,
        # Printed opening/closing balance discovery isn't attempted in this
        # pass (unvalidated against real statements); the running-balance
        # chain and printed-totals checks above already catch the same class
        # of extraction errors. Left as None (not attempted) rather than
        # guessed, per the fail-closed philosophy (doc section 38).
        opening_closing_reconciled=None,
        debit_total_reconciled=debit_reconciled,
        credit_total_reconciled=credit_reconciled,
        movement_count_reconciled=movement_count_reconciled,
        warnings=warnings,
        score=0.0,
    )
