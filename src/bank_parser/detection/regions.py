"""Transaction-region detection (doc sections 11, 16).

Bounds the extent of the primary transaction table: the header family that
repeats across the most pages/occurrences is treated as primary (a one-off
table shaped like a header, e.g. a credit-card installments breakdown, is
real but secondary -- doc section 24's risk about multiple table-shaped
regions per page). The region runs from just after that family's first
occurrence to the first generic "we've left the transaction section" marker
found afterward, or the end of the document.

The region is deliberately generous rather than exactly tight: anything
inside it that isn't actually a transaction gets filtered out later by
detection.classification.classify_row, which is a more reliable place to
make that call than a boundary heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass

from bank_parser.geometry import cluster_by_y, normalize_token
from bank_parser.detection.columns import ColumnLayout, infer_column_boundaries
from bank_parser.detection.headers import HeaderCandidate
from bank_parser.models.document import DocumentWord, SpatialDocument
from bank_parser.parsing.money import looks_like_money

# Generic, bank-agnostic markers that a statement has left the transaction
# table and entered a different report section (doc section 16). Matched as
# a substring of a short, money-free line only -- never against a full
# transaction row -- so a real transaction description containing e.g.
# "COMISION" as a line item is never mistaken for a section title.
STOP_PHRASES = {
    "resumen",
    "total de movimientos",
    "total movimientos",
    "total importe",
    "informacion importante",
    "aclaraciones",
    "aclaratorias",
    "comisiones",
    "intereses",
    "tasa de interes",
    "atencion de quejas",
}

_STOP_LINE_MAX_WORDS = 8


@dataclass
class TransactionRegion:
    page_start: int
    y_start: float
    page_end: int
    y_end: float
    header: HeaderCandidate
    column_layout: ColumnLayout


def _header_signature(header: HeaderCandidate) -> frozenset[str]:
    return frozenset(header.column_anchors.keys())


def _group_header_families(headers: list[HeaderCandidate]) -> list[list[HeaderCandidate]]:
    families: dict[frozenset[str], list[HeaderCandidate]] = {}
    for header in headers:
        families.setdefault(_header_signature(header), []).append(header)
    return list(families.values())


def _is_stop_line(line: list[DocumentWord]) -> bool:
    if len(line) > _STOP_LINE_MAX_WORDS:
        return False
    if any(looks_like_money(w.text) for w in line):
        return False
    text = " ".join(normalize_token(w.text) for w in line)
    return any(phrase in text for phrase in STOP_PHRASES)


def _find_stop_point(
    document: SpatialDocument, start_page: int, start_y: float
) -> tuple[int, float] | None:
    for page in document.pages:
        if page.page_number < start_page:
            continue
        lower_bound = start_y if page.page_number == start_page else 0.0
        words = [w for w in page.words if w.y_center >= lower_bound]
        for line in cluster_by_y(words):
            if _is_stop_line(line):
                return page.page_number, min(w.y0 for w in line)
    return None


def detect_transaction_regions(
    document: SpatialDocument, headers: list[HeaderCandidate]
) -> list[TransactionRegion]:
    if not headers:
        return []

    families = _group_header_families(headers)
    primary = max(families, key=lambda occurrences: (len(occurrences), occurrences[0].score))
    primary.sort(key=lambda h: (h.page, h.y0))

    first = primary[0]
    layout = infer_column_boundaries(first, document.page(first.page).width)

    stop = _find_stop_point(document, first.page, first.y1)
    if stop:
        page_end, y_end = stop
    else:
        last_page = document.pages[-1]
        page_end, y_end = last_page.page_number, last_page.height

    return [
        TransactionRegion(
            page_start=first.page,
            y_start=first.y1,
            page_end=page_end,
            y_end=y_end,
            header=first,
            column_layout=layout,
        )
    ]
