"""Render PDF pages to PNG bytes, for a UI to display alongside extracted
data (doc section 3.2: "Display PDF regions alongside extracted
transactions"). Display-only -- never feeds back into extraction, and stays
UI-framework-agnostic (returns raw bytes; a caller like app.py hands them to
st.image()).
"""

from __future__ import annotations

import pymupdf

from bank_parser.pdf.reader import PdfSource, open_document


def render_page_to_png(source: PdfSource, page_number: int, zoom: float = 1.5) -> bytes:
    """`page_number` is 1-indexed, matching the rest of the package."""
    doc = open_document(source)
    try:
        page = doc[page_number - 1]
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        return pixmap.tobytes("png")
    finally:
        doc.close()
