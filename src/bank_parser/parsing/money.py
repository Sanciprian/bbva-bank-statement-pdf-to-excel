"""Decimal money parsing (doc section 18). Never floats: every value that
survives here is an exact `Decimal`, so arithmetic in the validation layer
can compare cent-for-cent without floating-point drift.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from bank_parser.models.transaction import MoneyValue

_STRIP_RE = re.compile(r"[^\d.,]")
_VALID_RE = re.compile(r"^\d{1,3}(,\d{3})*\.\d{2}$|^\d+\.\d{2}$")


def parse_money(text: str) -> MoneyValue | None:
    """Handles: 1,234.56 / $1,234.56 / -1,234.56 / 1,234.56- / (1,234.56) /
    1 234.56. Returns None for anything that doesn't unambiguously look like
    a money amount, rather than guessing."""
    raw = text
    s = text.strip()
    if not s:
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    if s.endswith("-"):
        negative = True
        s = s[:-1].strip()
    if s.startswith("-"):
        negative = True
        s = s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()

    s = _STRIP_RE.sub("", s)  # drop currency symbols and whitespace (also handles "1 234.56")
    if not _VALID_RE.match(s):
        return None

    try:
        value = Decimal(s.replace(",", ""))
    except InvalidOperation:
        return None

    if negative:
        value = -value
    return MoneyValue(raw_text=raw, value=value)


def looks_like_money(text: str) -> bool:
    return parse_money(text) is not None
