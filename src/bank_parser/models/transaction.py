"""Row-level and transaction-level types produced as words are grouped into
rows, classified, and normalized (doc sections 13, 17-20)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from bank_parser.models.document import DocumentWord


class RowType(Enum):
    TRANSACTION = "transaction"
    CONTINUATION = "continuation"
    HEADER = "header"
    REPEATED_HEADER = "repeated_header"
    SUMMARY = "summary"
    FOOTER = "footer"
    UNKNOWN = "unknown"


@dataclass
class MoneyValue:
    raw_text: str
    value: Decimal
    currency: str | None = None


@dataclass
class ParsedDate:
    raw_text: str
    value: date | None


@dataclass
class DetectedRow:
    page: int
    y0: float
    y1: float
    cells: dict[str, list[DocumentWord]] = field(default_factory=dict)
    raw_words: list[DocumentWord] = field(default_factory=list)

    def text_in(self, column: str) -> str:
        words = sorted(self.cells.get(column, []), key=lambda w: w.x0)
        return " ".join(w.text for w in words)


@dataclass
class ClassifiedRow:
    row: DetectedRow
    row_type: RowType
    confidence: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class Transaction:
    transaction_date: date | None
    posting_date: date | None
    description: str
    debit: Decimal | None
    credit: Decimal | None
    amount: Decimal | None
    balance: Decimal | None
    reference: str | None
    source_page: int
    source_bbox: tuple[float, float, float, float] | None
    confidence: float
    raw_date_text: str | None = None
    raw_lines: list[str] = field(default_factory=list)

    def add_detail(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.raw_lines.append(text)
        self.description = f"{self.description} {text}".strip() if self.description else text
