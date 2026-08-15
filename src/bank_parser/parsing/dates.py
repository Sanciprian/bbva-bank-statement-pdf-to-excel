"""Date parsing with statement-period-based year inference (doc section 19).

Handles three shapes seen across statement families: a full numeric date
(with year), a named-month date (with year), and a named-month date with NO
year -- the last requires the statement's own printed period to resolve,
including the December-to-January rollover.
"""

from __future__ import annotations

import re
from datetime import date

from bank_parser.geometry import cluster_by_y
from bank_parser.models.document import SpatialDocument
from bank_parser.models.transaction import ParsedDate

MONTHS_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}
MONTHS_EN = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_FULL_NUMERIC_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")
_NAMED_MONTH_YEAR_RE = re.compile(r"^(\d{1,2})[-/]([A-Za-z]+)[-/](\d{4})$")
_NAMED_MONTH_NO_YEAR_RE = re.compile(r"^(\d{1,2})[/-]([A-Za-z]+)\.?$")
_TWO_NUMERIC_DATES_RE = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})")

_PERIOD_SEARCH_PAGES = 3


def _month_lookup(name: str) -> int | None:
    key = name.strip().lower()[:3]
    return MONTHS_ES.get(key) or MONTHS_EN.get(key)


def looks_like_date(text: str) -> bool:
    text = text.strip()
    if _FULL_NUMERIC_RE.match(text) or _NAMED_MONTH_YEAR_RE.match(text):
        return True
    m = _NAMED_MONTH_NO_YEAR_RE.match(text)
    return bool(m and _month_lookup(m.group(2)) is not None)


def parse_date(raw_text: str, period: tuple[date, date] | None = None) -> ParsedDate:
    text = raw_text.strip()

    m = _FULL_NUMERIC_RE.match(text)
    if m:
        day, month, year = (int(x) for x in m.groups())
        try:
            return ParsedDate(raw_text, date(year, month, day))
        except ValueError:
            return ParsedDate(raw_text, None)

    m = _NAMED_MONTH_YEAR_RE.match(text)
    if m:
        day_str, month_name, year_str = m.groups()
        month = _month_lookup(month_name)
        if month is not None:
            try:
                return ParsedDate(raw_text, date(int(year_str), month, int(day_str)))
            except ValueError:
                pass
        return ParsedDate(raw_text, None)

    m = _NAMED_MONTH_NO_YEAR_RE.match(text)
    if m:
        day_str, month_name = m.groups()
        month = _month_lookup(month_name)
        if month is None:
            return ParsedDate(raw_text, None)
        day = int(day_str)

        candidates: list[date] = []
        if period:
            for year in {period[0].year, period[1].year}:
                try:
                    candidate = date(year, month, day)
                except ValueError:
                    continue
                if period[0] <= candidate <= period[1]:
                    candidates.append(candidate)
        if candidates:
            return ParsedDate(raw_text, min(candidates))

        fallback_year = period[1].year if period else date.today().year
        try:
            return ParsedDate(raw_text, date(fallback_year, month, day))
        except ValueError:
            return ParsedDate(raw_text, None)

    return ParsedDate(raw_text, None)


def parse_period(document: SpatialDocument) -> tuple[date, date] | None:
    """Find the statement's printed period by looking for a line carrying
    two full numeric dates (a common, bank-agnostic "DD/MM/YYYY ... DD/MM/YYYY"
    shape) near the top of the document."""
    for page in document.pages[:_PERIOD_SEARCH_PAGES]:
        for line in cluster_by_y(page.words):
            text = " ".join(w.text for w in line)
            matches = _TWO_NUMERIC_DATES_RE.findall(text)
            if len(matches) < 2:
                continue
            dates = []
            for day_str, month_str, year_str in matches[:2]:
                try:
                    dates.append(date(int(year_str), int(month_str), int(day_str)))
                except ValueError:
                    continue
            if len(dates) == 2:
                return (min(dates), max(dates))
    return None
