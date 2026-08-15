"""BankStatement(s) -> pandas DataFrame (doc section 8's final "review
DataFrame" stage)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from bank_parser.models.statement import BankStatement

COLUMNS = [
    "source_file",
    "transaction_date",
    "posting_date",
    "description",
    "debit",
    "credit",
    "amount",
    "balance",
    "confidence",
]


def statement_to_dataframe(statement: "BankStatement") -> "pd.DataFrame":
    return statements_to_dataframe([statement])


def statements_to_dataframe(statements: list["BankStatement"]) -> "pd.DataFrame":
    import pandas as pd

    rows = [
        {
            "source_file": statement.source_filename,
            "transaction_date": txn.transaction_date,
            "posting_date": txn.posting_date,
            "description": txn.description,
            "debit": float(txn.debit) if txn.debit is not None else None,
            "credit": float(txn.credit) if txn.credit is not None else None,
            "amount": float(txn.amount) if txn.amount is not None else None,
            "balance": float(txn.balance) if txn.balance is not None else None,
            "confidence": txn.confidence,
        }
        for statement in statements
        for txn in statement.transactions
    ]
    return pd.DataFrame(rows, columns=COLUMNS)
