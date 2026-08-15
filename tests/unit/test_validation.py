from datetime import date
from decimal import Decimal

from bank_parser.models.transaction import Transaction
from bank_parser.validation.balances import check_running_balance_chain
from bank_parser.validation.totals import PrintedTotals
from bank_parser.validation.validator import validate_statement


def _txn(day, amount, balance, debit=None, credit=None):
    return Transaction(
        transaction_date=date(2025, 10, day),
        posting_date=date(2025, 10, day),
        description=f"txn {day}",
        debit=debit,
        credit=credit,
        amount=Decimal(str(amount)),
        balance=Decimal(str(balance)) if balance is not None else None,
        reference=None,
        source_page=1,
        source_bbox=None,
        confidence=0.9,
    )


def test_balance_chain_all_pass():
    txns = [
        _txn(1, "-100.00", "900.00", debit=Decimal("100.00")),
        _txn(2, "50.00", "950.00", credit=Decimal("50.00")),
        _txn(3, "-25.00", "925.00", debit=Decimal("25.00")),
    ]
    checks, passes, errors = check_running_balance_chain(txns)
    assert checks == 2
    assert passes == 2
    assert errors == []


def test_balance_chain_flags_exactly_the_broken_link():
    txns = [
        _txn(1, "-100.00", "900.00", debit=Decimal("100.00")),
        _txn(2, "50.00", "999.00", credit=Decimal("50.00")),  # should be 950.00
        _txn(3, "-25.00", "974.00", debit=Decimal("25.00")),  # re-anchors on 999.00 -> consistent
    ]
    checks, passes, errors = check_running_balance_chain(txns)
    assert checks == 2
    assert passes == 1
    assert len(errors) == 1
    assert "txn 2" in errors[0]


def test_validate_statement_reconciles_matching_totals():
    txns = [
        _txn(1, "-100.00", "900.00", debit=Decimal("100.00")),
        _txn(2, "50.00", "950.00", credit=Decimal("50.00")),
    ]
    totals = PrintedTotals(debit_total=Decimal("100.00"), credit_total=Decimal("50.00"))
    validation = validate_statement(txns, totals)
    assert validation.debit_total_reconciled is True
    assert validation.credit_total_reconciled is True
    assert validation.is_reliable is True


def test_validate_statement_flags_mismatched_totals():
    txns = [_txn(1, "-100.00", "900.00", debit=Decimal("100.00"))]
    totals = PrintedTotals(debit_total=Decimal("999.00"))
    validation = validate_statement(txns, totals)
    assert validation.debit_total_reconciled is False
    assert validation.is_reliable is False
    assert any("debit total mismatch" in w for w in validation.warnings)


def test_validate_statement_leaves_unattempted_checks_as_none():
    txns = [_txn(1, "-100.00", None, debit=Decimal("100.00"))]
    validation = validate_statement(txns, PrintedTotals())
    assert validation.debit_total_reconciled is None
    assert validation.credit_total_reconciled is None
    assert validation.movement_count_reconciled is None
    # No checks were attempted at all, so nothing failed -- reliable by default.
    assert validation.is_reliable is True
