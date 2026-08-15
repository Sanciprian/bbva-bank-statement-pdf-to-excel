"""Bank-independent statement representation (doc section 21)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from bank_parser.models.transaction import Transaction
from bank_parser.models.validation import StatementValidation

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class BankStatement:
    source_filename: str
    institution: str | None
    account_number_masked: str | None
    currency: str | None
    period_start: date | None
    period_end: date | None
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    transactions: list[Transaction] = field(default_factory=list)
    confidence: float = 0.0
    validation: StatementValidation = field(default_factory=StatementValidation)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dataframe(self) -> "pd.DataFrame":
        from bank_parser.export.dataframe import statement_to_dataframe

        return statement_to_dataframe(self)

    def to_csv(self, target: str | Path | IO[bytes]) -> None:
        from bank_parser.export.csv_exporter import write_csv

        write_csv(self.to_dataframe(), target)

    def to_excel(self, target: str | Path | IO[bytes]) -> None:
        from bank_parser.export.excel_exporter import write_excel

        write_excel([self], target)
