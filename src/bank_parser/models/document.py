"""Geometry-preserving representation of a PDF: words with page coordinates.

Every downstream stage (header detection, column inference, row
reconstruction) operates on these types rather than on raw PyMuPDF/camelot
objects, so the extraction backend can change without touching the rest of
the pipeline (see doc section 10).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DocumentWord:
    text: str
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    block_number: int | None = None
    line_number: int | None = None
    word_number: int | None = None

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class SpatialPage:
    page_number: int
    width: float
    height: float
    words: list[DocumentWord] = field(default_factory=list)

    def words_in_band(self, y0: float, y1: float) -> list[DocumentWord]:
        """Words whose vertical center falls inside [y0, y1]."""
        return [w for w in self.words if y0 <= w.y_center <= y1]

    def words_below(self, y: float) -> list[DocumentWord]:
        return [w for w in self.words if w.y_center >= y]


@dataclass
class SpatialDocument:
    pages: list[SpatialPage]
    source_filename: str

    def all_words(self) -> list[DocumentWord]:
        return [w for page in self.pages for w in page.words]

    def page(self, page_number: int) -> SpatialPage:
        return self.pages[page_number - 1]


@dataclass
class PageInfo:
    page_number: int
    width: float
    height: float
    rotation: int
    word_count: int
    block_count: int
    has_extractable_text: bool


@dataclass
class DocumentInfo:
    filename: str
    page_count: int
    pages: list[PageInfo]

    @property
    def is_supported(self) -> bool:
        """False when the document has effectively no extractable text
        (e.g. an image-only/scanned PDF) -- V1 has no OCR, so such a
        document should be rejected explicitly rather than silently
        producing an empty or garbage result (doc section 9)."""
        return any(page.has_extractable_text for page in self.pages)
