"""Tests for the bbva parsing pipeline.

Two layers:

* Unit tests — synthetic data only, always run, safe to commit.
* Integration tests — run the real parsers over whatever PDFs are in ``input/``
  and assert every statement reconciles. Skipped automatically when ``input/``
  is empty (e.g. on a fresh clone), so the suite never needs real bank data.

Run with:  python -m pytest tests/ -v
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bbva import detect, models, parse_credit, parse_debit
from bbva.dates import parse_credit_date, parse_debit_date, parse_period
from bbva.layout import group_into_rows, parse_money
from bbva.parse_debit import _validate_balance_chain

INPUT_DIR = Path(__file__).resolve().parent.parent / "input"


# ---------------------------------------------------------------- unit: money

@pytest.mark.parametrize(
    "text,expected",
    [
        ("$1,023.50", 1023.50),
        ("1,023.50", 1023.50),
        ("-$363.00", 363.00),
        ("363.00-", 363.00),
        ("19.50", 19.50),
        ("242,321.93", 242321.93),
    ],
)
def test_parse_money_valid(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize("text", ["", "hello", "12", "12.5", "1.2.3", "12/OCT", None])
def test_parse_money_rejects_non_money(text):
    assert parse_money(text) is None


# ---------------------------------------------------------------- unit: dates

def test_credit_date():
    assert parse_credit_date("24-dic-2025") == date(2025, 12, 24)
    assert parse_credit_date("1-ene-2026") == date(2026, 1, 1)
    assert parse_credit_date("24-xxx-2025") is None
    assert parse_credit_date("24/12/2025") is None


def test_period_parsing():
    period = parse_period("Periodo DEL 09/10/2025 AL 08/11/2025")
    assert period == (date(2025, 10, 9), date(2025, 11, 8))


def test_debit_year_inference_simple():
    period = (date(2026, 5, 9), date(2026, 6, 8))
    assert parse_debit_date("15/MAY", period) == date(2026, 5, 15)
    assert parse_debit_date("01/JUN", period) == date(2026, 6, 1)


def test_debit_year_inference_december_january_rollover():
    period = (date(2025, 12, 9), date(2026, 1, 8))
    assert parse_debit_date("28/DIC", period) == date(2025, 12, 28)
    assert parse_debit_date("03/ENE", period) == date(2026, 1, 3)


# ------------------------------------------------------------- unit: layout

def test_group_into_rows_merges_by_vertical_position():
    words = [
        {"x0": 10, "x1": 20, "top": 100.0, "bottom": 110, "text": "b"},
        {"x0": 0, "x1": 8, "top": 101.5, "bottom": 111, "text": "a"},  # same row
        {"x0": 0, "x1": 8, "top": 120.0, "bottom": 130, "text": "c"},  # next row
    ]
    rows = group_into_rows(words)
    assert [[w["text"] for w in r] for r in rows] == [["a", "b"], ["c"]]


# ------------------------------------------- unit: balance-chain validation

def _tx(out=None, inc=None, bal=None, desc="X"):
    return models.Transaction(
        source_file="t.pdf", statement_type=models.DEBIT,
        fecha_operacion=date(2026, 5, 1), description=desc,
        money_out=out, money_in=inc, balance=bal,
    )


def test_balance_chain_accepts_valid_chain():
    txns = [
        _tx(inc=100.0, bal=1100.0),
        _tx(out=50.0),               # no saldo printed (same-moment group)
        _tx(out=25.0, bal=1025.0),   # 1100 - 50 - 25
    ]
    assert _validate_balance_chain(txns) == []


def test_balance_chain_flags_broken_row():
    txns = [
        _tx(inc=100.0, bal=1100.0),
        _tx(out=50.0, bal=999.0),    # should be 1050
    ]
    errors = _validate_balance_chain(txns)
    assert len(errors) == 1
    assert "999.00" in errors[0] and "1050.00" in errors[0]


def test_balance_chain_reanchors_after_error():
    # One bad checkpoint must not cascade into errors on later good rows.
    txns = [
        _tx(inc=100.0, bal=1100.0),
        _tx(out=50.0, bal=999.0),   # bad
        _tx(out=99.0, bal=900.0),   # good relative to the re-anchored 999
    ]
    assert len(_validate_balance_chain(txns)) == 1


# ----------------------------------------------------- unit: reconciliation

def _result(**kw):
    r = models.StatementResult(source_file="t.pdf", statement_type="debit")
    for k, v in kw.items():
        setattr(r, k, v)
    return r


def test_reconciled_requires_totals():
    r = _result(printed_cargos=100.0, extracted_cargos=100.0,
                printed_abonos=50.0, extracted_abonos=50.0)
    assert r.reconciled

    r.extracted_cargos = 99.0
    assert not r.reconciled
    assert any("cargos" in f for f in r.check_failures())


def test_missing_printed_totals_fail_closed():
    # If we can't find BBVA's printed totals, the statement must NOT pass.
    r = _result(printed_cargos=None, extracted_cargos=100.0,
                printed_abonos=50.0, extracted_abonos=50.0)
    assert not r.reconciled


def test_count_check():
    r = _result(printed_cargos=50.0, extracted_cargos=50.0,
                printed_abonos=0.0, extracted_abonos=0.0,
                printed_count_cargos=2, printed_count_abonos=0)
    r.transactions = [_tx(out=25.0), _tx(out=25.0)]
    assert r.counts_ok and r.reconciled

    r.transactions.append(_tx(out=0.0))  # extra no-amount row doesn't count
    assert r.counts_ok
    r.transactions.append(_tx(out=10.0))  # a third cargo row breaks the count
    assert not r.counts_ok
    assert not r.reconciled


def test_chain_errors_break_reconciliation():
    r = _result(printed_cargos=50.0, extracted_cargos=50.0,
                printed_abonos=0.0, extracted_abonos=0.0)
    assert r.reconciled
    r.balance_chain_errors = ["balance chain broken at ..."]
    assert not r.reconciled


# ------------------------------------------------------ unit: fail-closed detect

class _FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class _FakePDF:
    def __init__(self, text):
        self.pages = [_FakePage(text)]


def test_detect_known_formats():
    assert detect.detect_format(_FakePDF("... DESGLOSE DE MOVIMIENTOS ...")) == models.CREDIT_REGULAR
    assert detect.detect_format(_FakePDF("... Detalle de Movimientos Realizados ...")) == models.DEBIT


def test_detect_unknown_format_raises():
    with pytest.raises(ValueError, match="unrecognized"):
        detect.detect_format(_FakePDF("some totally different bank layout"))


# ------------------------------------------------- integration: real PDFs

def _real_pdfs():
    return sorted(INPUT_DIR.glob("*.pdf")) if INPUT_DIR.is_dir() else []


@pytest.mark.skipif(not _real_pdfs(), reason="no statement PDFs in input/")
@pytest.mark.parametrize("pdf_path", _real_pdfs(), ids=lambda p: p.stem[-9:])
def test_real_statement_reconciles(pdf_path):
    pdfplumber = pytest.importorskip("pdfplumber")
    with pdfplumber.open(pdf_path) as pdf:
        fmt = detect.detect_format(pdf)
        if fmt == models.DEBIT:
            result = parse_debit.parse(pdf, pdf_path.name)
        else:
            result = parse_credit.parse(pdf, pdf_path.name)

    assert result.transactions, "no transactions extracted"
    assert result.reconciled, f"checks failed: {result.check_failures()}"
    # Every transaction must carry a date and exactly one of out/in.
    for t in result.transactions:
        assert t.fecha_operacion is not None
        assert not (t.money_out and t.money_in)
        assert t.description.strip()
    # All dates inside (or near) the statement period.
    if result.period:
        start, end = result.period
        for t in result.transactions:
            assert start <= t.fecha_operacion <= end, (
                f"{t.fecha_operacion} outside period {start}..{end}"
            )
