"""Column-boundary inference from header anchors (doc section 12).

Boundaries are always derived at runtime from the detected header's own
geometry (the midpoint between adjacent anchors) or from page dimensions --
never a literal coordinate tuned to one PDF.
"""

from __future__ import annotations

from dataclasses import dataclass

from bank_parser.detection.headers import HeaderCandidate


@dataclass
class ColumnBoundary:
    name: str
    x0: float
    x1: float
    anchor_x: float


@dataclass
class ColumnLayout:
    boundaries: list[ColumnBoundary]

    def classify_x(self, x_center: float) -> str | None:
        for boundary in self.boundaries:
            if boundary.x0 <= x_center < boundary.x1:
                return boundary.name
        if self.boundaries and x_center >= self.boundaries[-1].x1:
            return self.boundaries[-1].name
        return None

    @property
    def names(self) -> list[str]:
        return [b.name for b in self.boundaries]


def infer_column_boundaries(header: HeaderCandidate, page_width: float) -> ColumnLayout:
    ordered = sorted(header.column_anchors.items(), key=lambda item: item[1])
    boundaries: list[ColumnBoundary] = []

    for index, (name, anchor_x) in enumerate(ordered):
        left = 0.0 if index == 0 else (ordered[index - 1][1] + anchor_x) / 2
        right = page_width if index == len(ordered) - 1 else (anchor_x + ordered[index + 1][1]) / 2
        boundaries.append(ColumnBoundary(name=name, x0=left, x1=right, anchor_x=anchor_x))

    return ColumnLayout(boundaries=boundaries)
