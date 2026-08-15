"""Row classification with explainable reasons (doc section 17)."""

from __future__ import annotations

from bank_parser.detection.headers import HeaderCandidate
from bank_parser.models.document import SpatialDocument
from bank_parser.models.transaction import ClassifiedRow, DetectedRow, RowType
from bank_parser.parsing.dates import looks_like_date
from bank_parser.parsing.money import looks_like_money

_AMOUNT_COLUMNS = ("debit", "credit", "amount")
_WIDE_ROW_RATIO = 0.6


def _on_header_band(row: DetectedRow, headers: list[HeaderCandidate]) -> bool:
    return any(
        h.page == row.page and not (row.y1 < h.y0 or row.y0 > h.y1) for h in headers
    )


def classify_row(
    row: DetectedRow,
    headers: list[HeaderCandidate],
    prev: ClassifiedRow | None,
    page_width: float,
) -> ClassifiedRow:
    if _on_header_band(row, headers):
        return ClassifiedRow(
            row, RowType.REPEATED_HEADER, 0.95, ["row coincides with a detected header band"]
        )

    date_words = row.cells.get("date", [])
    amount_words = [w for column in _AMOUNT_COLUMNS for w in row.cells.get(column, [])]
    has_date = any(looks_like_date(w.text) for w in date_words)
    has_amount = any(looks_like_money(w.text) for w in amount_words)

    if has_date and has_amount:
        return ClassifiedRow(
            row,
            RowType.TRANSACTION,
            0.9,
            [
                "recognized date in date column",
                "monetary value aligned with a debit/credit/amount column",
            ],
        )

    if has_date or has_amount:
        return ClassifiedRow(
            row, RowType.UNKNOWN, 0.4, ["partial match: has a date or an amount but not both"]
        )

    xs = [w.x0 for w in row.raw_words] + [w.x1 for w in row.raw_words]
    row_span = (max(xs) - min(xs)) if xs else 0.0
    is_wide = page_width > 0 and row_span / page_width > _WIDE_ROW_RATIO

    description_words = row.cells.get("description", [])
    if description_words and not is_wide and prev is not None and prev.row_type in (
        RowType.TRANSACTION,
        RowType.CONTINUATION,
    ):
        return ClassifiedRow(
            row,
            RowType.CONTINUATION,
            0.7,
            ["no new date", "text lies in the description column", "continues the previous transaction"],
        )

    if is_wide:
        return ClassifiedRow(
            row,
            RowType.FOOTER,
            0.6,
            ["spans most of the page width -- looks like disclosure/footer text"],
        )

    return ClassifiedRow(
        row, RowType.UNKNOWN, 0.3, ["no date, no monetary value, and no continuation context"]
    )


def classify_rows(
    rows: list[DetectedRow], headers: list[HeaderCandidate], document: SpatialDocument
) -> list[ClassifiedRow]:
    page_widths = {page.page_number: page.width for page in document.pages}
    classified: list[ClassifiedRow] = []
    prev: ClassifiedRow | None = None

    for row in rows:
        current = classify_row(row, headers, prev, page_widths.get(row.page, 0.0))
        classified.append(current)
        prev = current

    return classified
