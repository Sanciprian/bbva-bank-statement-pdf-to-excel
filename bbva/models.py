"""Canonical transaction schema shared across parsers."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import List, Optional, Tuple

# Statement type tags.
CREDIT_REGULAR = "credit_regular"
CREDIT_INSTALLMENT = "credit_installment"
DEBIT = "debit"

# Canonical column order for the Excel "Transactions" sheet.
COLUMNS = [
    "source_file",
    "statement_type",
    "fecha_operacion",
    "fecha_cargo",
    "description",
    "details",
    "money_out",
    "money_in",
    "balance",
    "category",
]


@dataclass
class Transaction:
    """A single statement movement.

    ``money_out`` and ``money_in`` are stored as positive numbers (or ``None``).
    A row never has both populated.
    """

    source_file: str
    statement_type: str
    fecha_operacion: Optional[date] = None
    fecha_cargo: Optional[date] = None
    description: str = ""
    details: str = ""
    money_out: Optional[float] = None
    money_in: Optional[float] = None
    balance: Optional[float] = None
    category: str = ""
    # ``True`` for the net-zero PROMOCION / TRASPASO internal pairs that are
    # excluded from the final output but kept for reconciliation.
    is_internal_transfer: bool = field(default=False, repr=False)

    def add_detail(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.details = f"{self.details} {text}".strip() if self.details else text

    def to_row(self) -> dict:
        row = asdict(self)
        row.pop("is_internal_transfer", None)
        return {col: row[col] for col in COLUMNS}


@dataclass
class StatementResult:
    """Everything extracted from one statement PDF."""

    source_file: str
    statement_type: str  # "credit" or "debit"
    period: Optional[Tuple[date, date]] = None
    # Final, output-ready transactions (internal transfers already removed).
    transactions: List[Transaction] = field(default_factory=list)
    # Installment-table rows (credit only), reported separately so they never
    # inflate the regular totals.
    installments: List[Transaction] = field(default_factory=list)
    # Reconciliation: printed totals vs what we summed from the regular table.
    printed_cargos: Optional[float] = None
    printed_abonos: Optional[float] = None
    extracted_cargos: Optional[float] = None
    extracted_abonos: Optional[float] = None

    @staticmethod
    def _close(a: Optional[float], b: Optional[float], tol: float = 0.05) -> bool:
        if a is None or b is None:
            return False
        return abs(a - b) <= tol

    @property
    def cargos_ok(self) -> bool:
        return self._close(self.printed_cargos, self.extracted_cargos)

    @property
    def abonos_ok(self) -> bool:
        return self._close(self.printed_abonos, self.extracted_abonos)

    @property
    def reconciled(self) -> bool:
        return self.cargos_ok and self.abonos_ok
