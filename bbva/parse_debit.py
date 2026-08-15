"""Parser for BBVA debit / checking-account statements.

Section ``Detalle de Movimientos Realizados`` with columns:
``OPER | LIQ | DESCRIPCION | REFERENCIA | CARGOS | ABONOS | SALDO OPERACION |
SALDO LIQUIDACION``. Amount columns are distinguished by horizontal position, so we
anchor column centers from the header row and assign each money word to the nearest
column. Dates are ``DD/MMM`` (no year) and are resolved from the statement period.

Records span several lines (RFC / Referencia / SPEI ids / counterparty); continuation
lines are appended to the active transaction's ``details``.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

import pdfplumber

from . import models
from .dates import parse_debit_date, parse_period
from .layout import Row, group_into_rows, parse_money, text_of

# DD/MMM at the very left of the row.
_DEBIT_DATE_RE = re.compile(r"^\d{1,2}/[a-zA-Z]{3}\.?$")
# Fallback column centers if the header is never located.
_FALLBACK_CENTERS = {"cargos": 399.0, "abonos": 441.0, "operacion": 488.0, "liquidacion": 565.0}
# Rows that signal the table has ended.
_END_RE = re.compile(r"Total de Movimientos|TOTAL IMPORTE", re.IGNORECASE)
# Continuation lines start within the description column band.
_DESC_BAND = (95.0, 220.0)


def parse(pdf: "pdfplumber.PDF", source_file: str) -> models.StatementResult:
    full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    result = models.StatementResult(source_file=source_file, statement_type="debit")
    result.period = parse_period(full_text)

    centers = _find_column_centers(pdf) or _FALLBACK_CENTERS
    txns: List[models.Transaction] = []
    last: Optional[models.Transaction] = None
    in_table = False

    for page in pdf.pages:
        rows = group_into_rows(page.extract_words())
        for row in rows:
            line = text_of(row)

            if _is_header_row(line):
                in_table = True
                last = None
                continue
            if _END_RE.search(line):
                in_table = False
                last = None
                continue
            if not in_table:
                continue

            first = str(row[0]["text"]).strip()
            if _DEBIT_DATE_RE.match(first) and float(row[0]["x0"]) < 30:
                tx = _parse_transaction_row(row, source_file, centers, result.period)
                if tx:
                    txns.append(tx)
                    last = tx
                continue

            # Continuation line: starts in the description band, no leading date.
            if last is not None and row and _DESC_BAND[0] <= float(row[0]["x0"]) <= _DESC_BAND[1]:
                last.add_detail(line)

    result.transactions = txns
    result.extracted_cargos = round(sum(t.money_out for t in txns if t.money_out), 2)
    result.extracted_abonos = round(sum(t.money_in for t in txns if t.money_in), 2)
    result.printed_cargos, result.printed_abonos = _parse_debit_totals(full_text)
    result.printed_count_cargos, result.printed_count_abonos = _parse_debit_counts(full_text)
    result.balance_chain_errors = _validate_balance_chain(txns)
    return result


def _is_header_row(line: str) -> bool:
    up = line.upper()
    return "DESCRIPCION" in up and "CARGOS" in up and "ABONOS" in up


def _find_column_centers(pdf: "pdfplumber.PDF") -> Optional[Dict[str, float]]:
    """Locate the CARGOS/ABONOS/OPERACION/LIQUIDACION header and return centers."""
    for page in pdf.pages[:4]:
        for row in group_into_rows(page.extract_words()):
            words = {str(w["text"]).upper(): w for w in row}
            if {"CARGOS", "ABONOS", "OPERACION", "LIQUIDACION"} <= set(words):
                return {
                    "cargos": _center(words["CARGOS"]),
                    "abonos": _center(words["ABONOS"]),
                    "operacion": _center(words["OPERACION"]),
                    "liquidacion": _center(words["LIQUIDACION"]),
                }
    return None


def _center(w) -> float:
    return (float(w["x0"]) + float(w["x1"])) / 2.0


def _parse_transaction_row(
    row: Row, source_file: str, centers: Dict[str, float], period
) -> Optional[models.Transaction]:
    op_date = parse_debit_date(str(row[0]["text"]), period)

    cargo_date = None
    body_start = 1
    if len(row) > 1 and _DEBIT_DATE_RE.match(str(row[1]["text"]).strip()) \
            and float(row[1]["x0"]) < 105:
        cargo_date = parse_debit_date(str(row[1]["text"]), period)
        body_start = 2

    desc_words: List[str] = []
    amounts: Dict[str, float] = {}
    for w in row[body_start:]:
        txt = str(w["text"]).strip()
        money = parse_money(txt)
        if money is not None and _center(w) >= 360:
            col = _nearest_column(_center(w), centers)
            # Keep the first value seen per column.
            amounts.setdefault(col, money)
        else:
            desc_words.append(txt)

    return models.Transaction(
        source_file=source_file,
        statement_type=models.DEBIT,
        fecha_operacion=op_date,
        fecha_cargo=cargo_date,
        description=" ".join(desc_words).strip(),
        money_out=amounts.get("cargos"),
        money_in=amounts.get("abonos"),
        # SALDO OPERACION is the true running balance in operation-date order
        # (LIQUIDACION reflects settlement order and appears stale on rows that
        # liquidate later), so prefer it.
        balance=amounts.get("operacion") or amounts.get("liquidacion"),
    )


def _nearest_column(center: float, centers: Dict[str, float]) -> str:
    return min(centers, key=lambda c: abs(centers[c] - center))


def _parse_debit_counts(text: str):
    """Movement counts printed next to the totals, e.g.
    ``TOTAL MOVIMIENTOS CARGOS 8`` / ``TOTAL MOVIMIENTOS ABONOS 3``."""
    cargos = abonos = None
    m = re.search(r"TOTAL MOVIMIENTOS CARGOS\s+(\d+)", text, re.IGNORECASE)
    if m:
        cargos = int(m.group(1))
    m = re.search(r"TOTAL MOVIMIENTOS ABONOS\s+(\d+)", text, re.IGNORECASE)
    if m:
        abonos = int(m.group(1))
    return cargos, abonos


def _validate_balance_chain(txns: List[models.Transaction]) -> List[str]:
    """Check that each printed SALDO OPERACION equals the previous saldo plus the
    signed amounts of the rows in between. Pinpoints the exact row a misparse hits,
    which the whole-statement totals check cannot do.

    BBVA only prints a saldo on the last row of a same-moment group, so rows with
    ``balance is None`` just accumulate into the expectation for the next checkpoint.
    """
    errors: List[str] = []
    expected = None
    for t in txns:
        delta = (t.money_in or 0.0) - (t.money_out or 0.0)
        if expected is not None:
            expected += delta
        if t.balance is None:
            continue
        if expected is not None and abs(expected - t.balance) > 0.01:
            errors.append(
                f"balance chain broken at {t.fecha_operacion} '{t.description[:40]}': "
                f"expected {expected:.2f}, statement says {t.balance:.2f}"
            )
        expected = t.balance  # re-anchor on the printed value either way
    return errors


def _parse_debit_totals(text: str):
    cargos = abonos = None
    m = re.search(r"TOTAL IMPORTE CARGOS\s+([\d,]+\.\d{2})", text, re.IGNORECASE)
    if m:
        cargos = parse_money(m.group(1))
    m = re.search(r"TOTAL IMPORTE ABONOS\s+([\d,]+\.\d{2})", text, re.IGNORECASE)
    if m:
        abonos = parse_money(m.group(1))
    return cargos, abonos
