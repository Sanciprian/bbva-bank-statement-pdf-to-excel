import json
from pathlib import Path

from bank_parser.parsing.statement_parser import StatementParser

_EXPECTED_COUNTS = json.loads((Path(__file__).parent / "expected_counts.json").read_text())


def test_every_real_statement_parses_and_reconciles(real_pdfs):
    parser = StatementParser()

    for pdf_path in real_pdfs:
        statement = parser.parse(pdf_path)

        assert statement.transactions, f"{pdf_path.name}: no transactions extracted"

        validation = statement.validation
        assert validation.running_balance_passes == validation.running_balance_checks, (
            f"{pdf_path.name}: balance chain failures -- {validation.warnings}"
        )
        assert validation.is_reliable, f"{pdf_path.name}: not reliable -- {validation.warnings}"
        assert validation.score >= 0.7, f"{pdf_path.name}: low confidence score {validation.score}"

        for txn in statement.transactions:
            assert txn.transaction_date is not None
            assert txn.description
            assert txn.amount is not None


def test_extracted_counts_match_known_good_baseline(real_pdfs):
    parser = StatementParser()

    for pdf_path in real_pdfs:
        expected = _EXPECTED_COUNTS.get(pdf_path.name)
        if expected is None:
            continue  # a PDF added to input/ without a baseline entry -- nothing to compare

        statement = parser.parse(pdf_path)
        assert len(statement.transactions) == expected["expected_transactions"], (
            f"{pdf_path.name}: expected {expected['expected_transactions']} transactions, "
            f"got {len(statement.transactions)}"
        )
        assert statement.validation.is_reliable == expected["expect_reconciled"]
