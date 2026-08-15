from datetime import date

import pytest

from bank_parser.parsing.dates import looks_like_date, parse_date


def test_full_numeric_date():
    result = parse_date("09/10/2025")
    assert result.value == date(2025, 10, 9)


def test_named_month_with_year_spanish():
    result = parse_date("26-dic-2025")
    assert result.value == date(2025, 12, 26)


def test_named_month_with_year_january():
    result = parse_date("08-ene-2026")
    assert result.value == date(2026, 1, 8)


def test_named_month_no_year_within_period():
    period = (date(2025, 10, 9), date(2025, 11, 8))
    result = parse_date("10/OCT", period)
    assert result.value == date(2025, 10, 10)


def test_december_to_january_rollover():
    period = (date(2025, 12, 9), date(2026, 1, 8))
    assert parse_date("28/DIC", period).value == date(2025, 12, 28)
    assert parse_date("03/ENE", period).value == date(2026, 1, 3)


def test_named_month_no_year_no_period_falls_back_to_today_year():
    result = parse_date("15/MAY")
    assert result.value == date(date.today().year, 5, 15)


def test_invalid_date_returns_none():
    assert parse_date("not a date").value is None
    assert parse_date("32/FEB").value is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("10/OCT", True),
        ("26-dic-2025", True),
        ("09/10/2025", True),
        ("SPEI", False),
        ("450.00", False),
    ],
)
def test_looks_like_date(text, expected):
    assert looks_like_date(text) is expected
