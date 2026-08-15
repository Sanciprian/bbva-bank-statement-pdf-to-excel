"""Row reconstruction: group words in a transaction region into visual rows
and assign each word to a semantic column by position (doc section 13)."""

from __future__ import annotations

from bank_parser.geometry import cluster_by_y
from bank_parser.detection.regions import TransactionRegion
from bank_parser.models.document import SpatialDocument
from bank_parser.models.transaction import DetectedRow


def reconstruct_rows(document: SpatialDocument, region: TransactionRegion) -> list[DetectedRow]:
    rows: list[DetectedRow] = []

    for page in document.pages:
        if page.page_number < region.page_start or page.page_number > region.page_end:
            continue

        y_lower = region.y_start if page.page_number == region.page_start else 0.0
        y_upper = region.y_end if page.page_number == region.page_end else page.height

        words = [w for w in page.words if y_lower <= w.y_center <= y_upper]
        for line in cluster_by_y(words):
            cells: dict[str, list] = {}
            for word in line:
                column = region.column_layout.classify_x(word.x_center)
                if column:
                    cells.setdefault(column, []).append(word)
            rows.append(
                DetectedRow(
                    page=page.page_number,
                    y0=min(w.y0 for w in line),
                    y1=max(w.y1 for w in line),
                    cells=cells,
                    raw_words=line,
                )
            )

    return rows
