from bank_parser.detection.columns import infer_column_boundaries
from bank_parser.detection.headers import HeaderCandidate


def test_infer_column_boundaries_from_anchors():
    header = HeaderCandidate(
        page=1,
        y0=100,
        y1=110,
        column_anchors={"date": 50, "description": 150, "debit": 350, "credit": 420, "balance": 500},
    )
    layout = infer_column_boundaries(header, page_width=600)

    assert layout.names == ["date", "description", "debit", "credit", "balance"]
    # First column starts at 0, last column ends at the page width.
    assert layout.boundaries[0].x0 == 0.0
    assert layout.boundaries[-1].x1 == 600.0
    # Boundaries between adjacent columns sit at the midpoint of their anchors.
    assert layout.boundaries[0].x1 == (50 + 150) / 2


def test_classify_x_uses_midpoint_boundaries():
    header = HeaderCandidate(
        page=1, y0=0, y1=10, column_anchors={"date": 50, "description": 150, "balance": 500}
    )
    layout = infer_column_boundaries(header, page_width=600)

    assert layout.classify_x(40) == "date"
    assert layout.classify_x(140) == "description"
    assert layout.classify_x(590) == "balance"


def test_no_hardcoded_coordinates_layout_moves_with_anchors():
    """The whole point of geometry-first detection: shifting every anchor by
    a constant offset must shift every boundary by the same offset -- nothing
    in the layout is pinned to an absolute page coordinate."""
    header_a = HeaderCandidate(page=1, y0=0, y1=10, column_anchors={"date": 50, "balance": 500})
    header_b = HeaderCandidate(page=1, y0=0, y1=10, column_anchors={"date": 150, "balance": 600})

    layout_a = infer_column_boundaries(header_a, page_width=600)
    layout_b = infer_column_boundaries(header_b, page_width=700)

    offset = 100
    assert layout_b.boundaries[0].x1 - layout_a.boundaries[0].x1 == offset
