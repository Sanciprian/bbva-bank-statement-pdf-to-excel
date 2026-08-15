"""Document inspection and the public PDF-reading entry point (doc section 9).

`read_pdf` refuses to guess on image-only/scanned PDFs -- V1 has no OCR, so an
unsupported document should fail loudly and explicitly rather than silently
producing an empty or garbage result (doc section 38).

Accepts either a filesystem path or raw PDF bytes (doc section 44's
`Path | bytes` signature) -- the bytes path lets a UI like Streamlit hand
over an uploaded file's contents directly, with no temporary file ever
touching disk.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from bank_parser.models.document import DocumentInfo, PageInfo, SpatialDocument
from bank_parser.pdf.spatial_document import build_spatial_document

PdfSource = str | Path | bytes


class UnsupportedDocumentError(Exception):
    """Raised when a PDF has no meaningfully extractable text layer."""


def open_document(source: PdfSource) -> "pymupdf.Document":
    """Open a `PdfSource` (path or bytes) as a live pymupdf.Document. Public
    so other pdf/ modules (e.g. render.py) share one place that knows how to
    open either kind of source -- callers are responsible for closing it."""
    if isinstance(source, bytes):
        return pymupdf.open(stream=source, filetype="pdf")
    return pymupdf.open(Path(source))


def inspect_document(source: PdfSource, filename: str | None = None) -> DocumentInfo:
    name = filename or (Path(source).name if not isinstance(source, bytes) else "uploaded.pdf")

    doc = open_document(source)
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
        return DocumentInfo(filename=name, page_count=doc.page_count, pages=pages)
    finally:
        doc.close()


def read_pdf(source: PdfSource, filename: str | None = None) -> SpatialDocument:
    info = inspect_document(source, filename=filename)
    if not info.is_supported:
        raise UnsupportedDocumentError(
            f"{info.filename}: this PDF appears to contain image-only pages. "
            "OCR is not enabled in the current version."
        )

    doc = open_document(source)
    try:
        return build_spatial_document(doc, source_filename=info.filename)
    finally:
        doc.close()
