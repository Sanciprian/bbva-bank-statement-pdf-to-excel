"""Parser for BBVA credit-card statements (``DESGLOSE DE MOVIMIENTOS``).

Two tables are extracted:

* ``COMPRAS Y CARGOS DIFERIDOS A MESES SIN INTERESES`` — installment purchases.
  ``Monto original`` is recorded as ``money_out`` and tagged ``credit_installment``.
* ``CARGOS,COMPRAS Y ABONOS REGULARES (NO A MESES)`` — regular movements where a
  leading ``+`` means a charge (``money_out``) and ``-`` means a payment/credit
  (``money_in``).

The net-zero ``PROMOCION MESES S/INT`` / ``TRASPASO A MESES SIN INTERES`` pairs are
flagged and counted for reconciliation, then removed from the output.
"""

from __future__ import annotations

import re
from typing import List, Optional

import pdfplumber

from . import models
from .dates import parse_credit_date
from .layout import Row, group_into_rows, parse_money, text_of, word_center

_SEC_INSTALLMENT = "installment"
_SEC_REGULAR = "regular"

_INTERNAL_RE = re.compile(r"PROMOCION MESES|TRASPASO A MESES", re.IGNORECASE)
# Header / footer rows that must never be treated as data.
_SKIP_RE = re.compile(
    r"Fecha de la|Descripción|operación|aplicable|Tasa de|Núm\.|"
    r"Notas:|Número de cuenta|Página|TOTAL CARGOS|TOTAL ABONOS|"
    r"Tarjeta titular|DESGLOSE DE MOVIMIENTOS",
    re.IGNORECASE,
)

_CREDIT_DATE_RE = re.compile(r"^\d{1,2}-[a-zA-Z]{3}-\d{4}$")


def parse(pdf: "pdfplumber.PDF", source_file: str) -> models.StatementResult:
    full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    result = models.StatementResult(source_file=source_file, statement_type="credit")
    result.period = _parse_credit_period(full_text)

    section: Optional[str] = None
    regular: List[models.Transaction] = []
    installments: List[models.Transaction] = []
    last_regular: Optional[models.Transaction] = None

    for page in pdf.pages:
        rows = group_into_rows(page.extract_words())
        for row in rows:
            line = text_of(row)
            upper = line.upper()

            if "COMPRAS Y CARGOS DIFERIDOS A MESES SIN INTERESES" in upper:
                section = _SEC_INSTALLMENT
                last_regular = None
                continue
            if "CARGOS,COMPRAS Y ABONOS REGULARES" in upper:
                section = _SEC_REGULAR
                last_regular = None
                continue
            if "TOTAL CARGOS" in upper or "TOTAL ABONOS" in upper:
                section = None
                last_regular = None
                continue
            if section is None or _SKIP_RE.search(line):
                continue

            if section == _SEC_INSTALLMENT:
                tx = _parse_installment_row(row, source_file)
                if tx:
                    installments.append(tx)
            elif section == _SEC_REGULAR:
                tx = _parse_regular_row(row, source_file)
                if tx:
                    regular.append(tx)
                    last_regular = tx
                elif last_regular is not None and "TIPO DE CAMBIO" in upper:
                    # Currency-conversion continuation line.
                    last_regular.add_detail(line)

    # Reconciliation uses the *full* regular table (internal transfers included),
    # because BBVA's printed TOTAL CARGOS/ABONOS include them.
    result.extracted_cargos = round(sum(t.money_out for t in regular if t.money_out), 2)
    result.extracted_abonos = round(sum(t.money_in for t in regular if t.money_in), 2)
    result.printed_cargos, result.printed_abonos = _parse_credit_totals(full_text)

    result.transactions = [t for t in regular if not t.is_internal_transfer]
    result.installments = installments
    return result


def _parse_installment_row(row: Row, source_file: str) -> Optional[models.Transaction]:
    if not row:
        return None
    first = str(row[0]["text"]).strip()
    if not _CREDIT_DATE_RE.match(first):
        return None
    op_date = parse_credit_date(first)
    if op_date is None:
        return None

    # Description = text words left of the money columns (center < 310).
    desc_words = [
        str(w["text"]) for w in row[1:]
        if word_center(w) < 310 and parse_money(str(w["text"])) is None
    ]
    # Monto original = leftmost money value in the row.
    money_words = sorted(
        (w for w in row if parse_money(str(w["text"])) is not None),
        key=word_center,
    )
    monto = parse_money(str(money_words[0]["text"])) if money_words else None

    return models.Transaction(
        source_file=source_file,
        statement_type=models.CREDIT_INSTALLMENT,
        fecha_operacion=op_date,
        description=" ".join(desc_words).strip(),
        money_out=monto,
    )


def _parse_regular_row(row: Row, source_file: str) -> Optional[models.Transaction]:
    if len(row) < 2:
        return None
    first = str(row[0]["text"]).strip()
    if not _CREDIT_DATE_RE.match(first):
        return None
    op_date = parse_credit_date(first)
    if op_date is None:
        return None

    cargo_date = None
    body_start = 1
    if len(row) > 1 and _CREDIT_DATE_RE.match(str(row[1]["text"]).strip()):
        cargo_date = parse_credit_date(str(row[1]["text"]).strip())
        body_start = 2

    # Sign token sits in the amount region (x0 > 480).
    sign = None
    amount = None
    desc_words: List[str] = []
    for w in row[body_start:]:
        txt = str(w["text"]).strip()
        x0 = float(w["x0"])
        if txt in ("+", "-") and x0 > 480:
            sign = txt
            continue
        money = parse_money(txt)
        if money is not None and x0 > 480:
            amount = money
            continue
        desc_words.append(txt)

    if amount is None or sign is None:
        return None

    description = " ".join(desc_words).strip()
    tx = models.Transaction(
        source_file=source_file,
        statement_type=models.CREDIT_REGULAR,
        fecha_operacion=op_date,
        fecha_cargo=cargo_date,
        description=description,
        money_out=amount if sign == "+" else None,
        money_in=amount if sign == "-" else None,
        is_internal_transfer=bool(_INTERNAL_RE.search(description)),
    )
    return tx


def _parse_credit_period(text: str):
    m = re.search(
        r"Periodo:\s*(\d{1,2}-[a-zA-Z]{3}-\d{4})\s+al\s+(\d{1,2}-[a-zA-Z]{3}-\d{4})",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    start = parse_credit_date(m.group(1))
    end = parse_credit_date(m.group(2))
    if start and end:
        return start, end
    return None


def _parse_credit_totals(text: str):
    cargos = abonos = None
    m = re.search(r"TOTAL CARGOS\s+-?\$?([\d,]+\.\d{2})", text, re.IGNORECASE)
    if m:
        cargos = parse_money("$" + m.group(1))
    m = re.search(r"TOTAL ABONOS\s+-?\$?([\d,]+\.\d{2})", text, re.IGNORECASE)
    if m:
        abonos = parse_money("$" + m.group(1))
    return cargos, abonos
