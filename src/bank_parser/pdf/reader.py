"""Document inspection and the public PDF-reading entry point (doc section 9).

`read_pdf` refuses to guess on image-only/scanned PDFs -- V1 has no OCR, so an
unsupported document should fail loudly and explicitly rather than silently
producing an empty or garbage result (doc section 38).
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from bank_parser.models.document import DocumentInfo, PageInfo, SpatialDocument
from bank_parser.pdf.spatial_document import build_spatial_document


class UnsupportedDocumentError(Exception):
    """Raised when a PDF has no meaningfully extractable text layer."""


def inspect_document(path: Path) -> DocumentInfo:
    doc = pymupdf.open(path)
    try:
        pages = []
        for index in range(doc.page_count):
            page = doc[index]
            words = page.get_text("words")
            blocks = page.get_text("blocks")
            pages.append(
                PageInfo(
                    page_number=index + 1,
                    width=page.rect.width,
                    height=page.rect.height,
                    rotation=page.rotation,
                    word_count=len(words),
                    block_count=len(blocks),
                    has_extractable_text=len(words) > 0,
                )
            )
        return DocumentInfo(filename=path.name, page_count=doc.page_count, pages=pages)
    finally:
        doc.close()


def read_pdf(path: Path) -> SpatialDocument:
    path = Path(path)
    info = inspect_document(path)
    if not info.is_supported:
        raise UnsupportedDocumentError(
            f"{path.name}: this PDF appears to contain image-only pages. "
            "OCR is not enabled in the current version."
        )

    doc = pymupdf.open(path)
    try:
        return build_spatial_document(doc, source_filename=path.name)
    finally:
        doc.close()
