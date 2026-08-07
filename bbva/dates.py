"""Spanish-language date parsing and year inference for BBVA statements.

BBVA credit statements print dates as ``DD-mmm-YYYY`` (year present). Debit/checking
statements print ``DD/MMM`` with **no year**, so the year must be inferred from the
statement period (``Periodo DEL dd/mm/yyyy AL dd/mm/yyyy``), correctly handling the
December -> January roll-over.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional, Tuple

# BBVA uses 3-letter Spanish month abbreviations (lower- or upper-case).
MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}

# 24-dic-2025  /  22-ene-2026
_CREDIT_RE = re.compile(r"^(\d{1,2})-([a-zA-Z]{3})-(\d{4})$")
# 10/OCT
_DEBIT_RE = re.compile(r"^(\d{1,2})/([a-zA-Z]{3})\.?$")
# 09/10/2025
_NUMERIC_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def parse_credit_date(token: str) -> Optional[date]:
    """Parse a ``DD-mmm-YYYY`` token. Returns ``None`` if it isn't one."""
    m = _CREDIT_RE.match(token.strip())
    if not m:
        return None
    day, mon, year = m.groups()
    month = MONTHS.get(mon.lower())
    if not month:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def parse_numeric_date(text: str) -> Optional[date]:
    """Parse a ``DD/MM/YYYY`` date found anywhere in ``text``."""
    m = _NUMERIC_RE.search(text)
    if not m:
        return None
    day, month, year = (int(x) for x in m.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_period(text: str) -> Optional[Tuple[date, date]]:
    """Extract (start, end) from ``Periodo DEL dd/mm/yyyy AL dd/mm/yyyy``."""
    m = re.search(
        r"DEL\s+(\d{1,2}/\d{1,2}/\d{4})\s+AL\s+(\d{1,2}/\d{1,2}/\d{4})",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    start = parse_numeric_date(m.group(1))
    end = parse_numeric_date(m.group(2))
    if start and end:
        return start, end
    return None


def parse_debit_date(token: str, period: Optional[Tuple[date, date]]) -> Optional[date]:
    """Parse a ``DD/MMM`` token, inferring the year from the statement period.

    Picks whichever candidate year places the date inside the period range; this
    resolves the December (start year) vs January (end year) ambiguity. Falls back
    to the period-end year when no period is available or neither candidate fits.
    """
    m = _DEBIT_RE.match(token.strip())
    if not m:
        return None
    day_s, mon_s = m.groups()
    month = MONTHS.get(mon_s.lower())
    if not month:
        return None
    day = int(day_s)

    if period is None:
        return _safe_date(date.today().year, month, day)

    start, end = period
    candidates = {start.year, end.year}
    in_range = [
        d for y in candidates
        if (d := _safe_date(y, month, day)) is not None and start <= d <= end
    ]
    if in_range:
        return min(in_range)
    # Neither candidate lands in range (e.g. a "fecha de cargo" just past corte):
    # use the year of whichever period boundary shares the month, else period end.
    if month == start.month:
        return _safe_date(start.year, month, day)
    return _safe_date(end.year, month, day)


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None
