"""Low-level helpers for working with pdfplumber word boxes."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional

# A word as returned by pdfplumber.Page.extract_words(): keys x0, x1, top, bottom, text.
Word = Dict[str, object]
Row = List[Word]

_MONEY_RE = re.compile(r"-?\$?\s?-?[\d,]+\.\d{2}-?")


def group_into_rows(words: List[Word], y_tol: float = 3.0) -> List[Row]:
    """Group words into visual rows by their vertical (``top``) position.

    Returns rows sorted top-to-bottom, each row's words sorted left-to-right.
    """
    buckets: Dict[float, Row] = defaultdict(list)
    for w in words:
        key = None
        for existing in buckets:
            if abs(existing - float(w["top"])) <= y_tol:
                key = existing
                break
        if key is None:
            key = float(w["top"])
        buckets[key].append(w)

    rows = []
    for top in sorted(buckets):
        rows.append(sorted(buckets[top], key=lambda x: float(x["x0"])))
    return rows


def word_center(w: Word) -> float:
    return (float(w["x0"]) + float(w["x1"])) / 2.0


def parse_money(text: str) -> Optional[float]:
    """Parse a peso amount like ``$1,023.50`` / ``-$363.00`` / ``19.50``.

    Returns the absolute value as a float (sign handling is the caller's job, since
    BBVA encodes direction via separate columns or a leading +/- token). Returns
    ``None`` when the text is not a money value.
    """
    if text is None:
        return None
    t = str(text).strip()
    if not _MONEY_RE.fullmatch(t):
        return None
    cleaned = t.replace("$", "").replace(",", "").replace(" ", "").strip("-")
    try:
        return abs(float(cleaned))
    except ValueError:
        return None


def text_of(row: Row) -> str:
    return " ".join(str(w["text"]) for w in row)
