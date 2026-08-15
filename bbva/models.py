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
    # Movement counts BBVA prints next to the totals (debit only; None = not printed).
    printed_count_cargos: Optional[int] = None
    printed_count_abonos: Optional[int] = None
    # Row-level running-balance validation (debit only). Each entry describes one
    # row whose SALDO does not equal previous SALDO +/- the row amounts.
    balance_chain_errors: List[str] = field(default_factory=list)

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
    def counts_ok(self) -> bool:
        """Extracted row counts vs the counts BBVA prints (vacuously true when
        the statement doesn't print counts, e.g. credit cards)."""
        if self.printed_count_cargos is not None:
            n = sum(1 for t in self.transactions if t.money_out)
            if n != self.printed_count_cargos:
                return False
        if self.printed_count_abonos is not None:
            n = sum(1 for t in self.transactions if t.money_in)
            if n != self.printed_count_abonos:
                return False
        return True

    @property
    def chain_ok(self) -> bool:
        return not self.balance_chain_errors

    @property
    def reconciled(self) -> bool:
        return self.cargos_ok and self.abonos_ok and self.counts_ok and self.chain_ok

    def check_failures(self) -> List[str]:
        """Human-readable list of every failed check (empty when reconciled)."""
        fails: List[str] = []
        if not self.cargos_ok:
            fails.append(f"cargos {self.extracted_cargos} != printed {self.printed_cargos}")
        if not self.abonos_ok:
            fails.append(f"abonos {self.extracted_abonos} != printed {self.printed_abonos}")
        if not self.counts_ok:
            n_out = sum(1 for t in self.transactions if t.money_out)
            n_in = sum(1 for t in self.transactions if t.money_in)
            fails.append(
                f"row counts {n_out} cargos/{n_in} abonos != printed "
                f"{self.printed_count_cargos}/{self.printed_count_abonos}"
            )
        fails.extend(self.balance_chain_errors)
        return fails
