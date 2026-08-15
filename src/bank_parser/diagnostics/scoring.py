"""Confidence scoring from measurable evidence, not an arbitrary number
(doc section 23)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfidenceComponents:
    header_detection: float = 0.0
    column_consistency: float = 0.0
    row_structure: float = 0.0
    date_parsing: float = 0.0
    money_parsing: float = 0.0
    running_balance: float = 0.0
    summary_reconciliation: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "header_detection": self.header_detection,
            "column_consistency": self.column_consistency,
            "row_structure": self.row_structure,
            "date_parsing": self.date_parsing,
            "money_parsing": self.money_parsing,
            "running_balance": self.running_balance,
            "summary_reconciliation": self.summary_reconciliation,
        }


def compute_confidence(components: ConfidenceComponents) -> float:
    values = list(components.as_dict().values())
    return sum(values) / len(values) if values else 0.0
