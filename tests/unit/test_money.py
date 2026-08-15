from decimal import Decimal

import pytest

from bank_parser.parsing.money import looks_like_money, parse_money


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1,234.56", Decimal("1234.56")),
        ("$1,234.56", Decimal("1234.56")),
        ("-1,234.56", Decimal("-1234.56")),
        ("1,234.56-", Decimal("-1234.56")),
        ("(1,234.56)", Decimal("-1234.56")),
        ("1 234.56", Decimal("1234.56")),
        ("450.00", Decimal("450.00")),
        ("+1,234.56", Decimal("1234.56")),
    ],
)
def test_parse_money_valid(text, expected):
    result = parse_money(text)
    assert result is not None
    assert result.value == expected
    assert result.raw_text == text


@pytest.mark.parametrize(
    "text",
    [
        "",
        "abc",
        "12.5",
        "12.345",
        "SPEI",
        "10/OCT",
    ],
)
def test_parse_money_invalid(text):
    assert parse_money(text) is None


def test_looks_like_money():
    assert looks_like_money("1,234.56") is True
    assert looks_like_money("FECHA") is False
