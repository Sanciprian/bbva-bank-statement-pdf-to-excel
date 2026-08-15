"""PyMuPDF word extraction, wrapped so the rest of the pipeline never touches
pymupdf objects directly (doc section 7)."""

from __future__ import annotations

import pymupdf

from bank_parser.models.document import DocumentWord, SpatialDocument, SpatialPage


def extract_words(page: "pymupdf.Page", page_number: int) -> list[DocumentWord]:
    """Wrap Page.get_text("words"), which returns
    (x0, y0, x1, y1, text, block_no, line_no, word_no) tuples."""
    return [
        DocumentWord(
            text=text,
            page=page_number,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            block_number=block_no,
            line_number=line_no,
            word_number=word_no,
        )
        for x0, y0, x1, y1, text, block_no, line_no, word_no in page.get_text("words")
    ]


def build_spatial_document(doc: "pymupdf.Document", source_filename: str) -> SpatialDocument:
    pages = []
    for index in range(doc.page_count):
        page = doc[index]
        page_number = index + 1
        pages.append(
            SpatialPage(
                page_number=page_number,
                width=page.rect.width,
                height=page.rect.height,
                words=extract_words(page, page_number),
            )
        )
    return SpatialDocument(pages=pages, source_filename=source_filename)
