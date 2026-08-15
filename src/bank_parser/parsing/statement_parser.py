"""The public orchestration entry point (doc section 44):

    statement = StatementParser().parse("statement.pdf")

Wires the whole pipeline together: read -> select profile -> detect header
-> detect region -> reconstruct rows -> classify -> normalize -> discover
printed totals -> validate -> score. Everything downstream of this file
(CLI, tests, a future UI) only ever touches the returned BankStatement.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path

from bank_parser.detection.classification import classify_rows
from bank_parser.detection.headers import find_header_candidates
from bank_parser.detection.regions import detect_transaction_regions
from bank_parser.detection.rows import reconstruct_rows
from bank_parser.diagnostics.scoring import ConfidenceComponents, compute_confidence
from bank_parser.models.statement import BankStatement
from bank_parser.models.validation import StatementValidation
from bank_parser.parsing.aliases import COLUMN_ALIASES
from bank_parser.parsing.dates import parse_period
from bank_parser.parsing.transaction_parser import normalize_transactions
from bank_parser.pdf.camelot_adapter import extract_tables
from bank_parser.pdf.reader import read_pdf
from bank_parser.profiles.base import BankProfile
from bank_parser.profiles.registry import KNOWN_PROFILES, select_profile
from bank_parser.validation.totals import find_printed_totals
from bank_parser.validation.validator import (
    transaction_direction,
    transaction_magnitude,
    validate_statement,
)


def _merged_aliases(profile: BankProfile) -> dict[str, set[str]]:
    merged = {category: set(words) for category, words in COLUMN_ALIASES.items()}
    for category, extra in profile.additional_column_aliases.items():
        merged.setdefault(category, set()).update(extra)
    return merged


def _summary_score(validation: StatementValidation) -> float:
    flags = [
        validation.debit_total_reconciled,
        validation.credit_total_reconciled,
        validation.movement_count_reconciled,
    ]
    attempted = [f for f in flags if f is not None]
    if not attempted:
        return 0.5
    return sum(1.0 for f in attempted if f) / len(attempted)


class StatementParser:
    def __init__(self, profiles: list[BankProfile] | None = None) -> None:
        self._profiles = profiles if profiles is not None else KNOWN_PROFILES

    def parse(self, pdf: str | Path) -> BankStatement:
        path = Path(pdf)
        document = read_pdf(path)
        profile = select_profile(document, self._profiles)

        headers = find_header_candidates(document, aliases=_merged_aliases(profile))
        regions = detect_transaction_regions(document, headers)

        if not regions:
            return BankStatement(
                source_filename=document.source_filename,
                institution=profile.bank_name if profile.identifying_phrases else None,
                account_number_masked=None,
                currency=None,
                period_start=None,
                period_end=None,
                opening_balance=None,
                closing_balance=None,
                transactions=[],
                confidence=0.0,
                validation=StatementValidation(warnings=["no transaction table detected"]),
                diagnostics={"profile": profile.bank_name},
            )

        # Single-candidate this pass -- see doc section 25 for the seam a
        # future multi-strategy candidate-and-selector architecture would use.
        region = regions[0]
        rows = reconstruct_rows(document, region)
        classified = classify_rows(rows, headers, document)
        period = parse_period(document)
        transactions = normalize_transactions(classified, region.column_layout, period, profile)

        # Best-effort/diagnostic only -- never blocks the pipeline (doc section 24).
        candidate_tables = extract_tables(path)

        totals = find_printed_totals(document, profile)
        validation = validate_statement(transactions, totals)

        debit_txns = [t for t in transactions if transaction_direction(t) == "debit"]
        credit_txns = [t for t in transactions if transaction_direction(t) == "credit"]
        extracted_debit_sum = sum((transaction_magnitude(t, "debit") for t in debit_txns), Decimal("0"))
        extracted_credit_sum = sum((transaction_magnitude(t, "credit") for t in credit_txns), Decimal("0"))

        row_counts = Counter(c.row_type.value for c in classified)
        transaction_like_rows = row_counts.get("transaction", 0) + row_counts.get("continuation", 0)
        total_rows = sum(row_counts.values()) or 1

        components = ConfidenceComponents(
            header_detection=region.header.score,
            column_consistency=min(len(region.column_layout.boundaries) / 4, 1.0),
            row_structure=transaction_like_rows / total_rows,
            date_parsing=1.0 if transactions else 0.0,
            money_parsing=(
                sum(1 for t in transactions if t.amount is not None) / len(transactions)
                if transactions
                else 0.0
            ),
            running_balance=(
                validation.running_balance_passes / validation.running_balance_checks
                if validation.running_balance_checks
                else 0.5
            ),
            summary_reconciliation=_summary_score(validation),
        )
        validation.score = compute_confidence(components)

        balances = [t.balance for t in transactions if t.balance is not None]

        return BankStatement(
            source_filename=document.source_filename,
            institution=profile.bank_name if profile.identifying_phrases else None,
            account_number_masked=None,
            currency=None,
            period_start=period[0] if period else None,
            period_end=period[1] if period else None,
            opening_balance=None,
            closing_balance=balances[-1] if balances else None,
            transactions=transactions,
            confidence=validation.score,
            validation=validation,
            diagnostics={
                "profile": profile.bank_name,
                "header_score": region.header.score,
                "region_pages": [region.page_start, region.page_end],
                "row_type_counts": dict(row_counts),
                "printed_totals": {
                    "debit_total": str(totals.debit_total) if totals.debit_total is not None else None,
                    "credit_total": str(totals.credit_total) if totals.credit_total is not None else None,
                    "debit_count": totals.debit_count,
                    "credit_count": totals.credit_count,
                },
                "extracted_debit_sum": extracted_debit_sum,
                "extracted_credit_sum": extracted_credit_sum,
                "debit_transaction_count": len(debit_txns),
                "credit_transaction_count": len(credit_txns),
                "camelot_candidate_tables": len(candidate_tables),
            },
        )
