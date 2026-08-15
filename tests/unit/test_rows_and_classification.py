from bank_parser.detection.classification import classify_row
from bank_parser.detection.headers import HeaderCandidate
from bank_parser.geometry import cluster_by_y
from bank_parser.models.document import DocumentWord
from bank_parser.models.transaction import ClassifiedRow, DetectedRow, RowType


def _word(text, x0, y0, x1=None, y1=None, page=1):
    return DocumentWord(text=text, page=page, x0=x0, y0=y0, x1=x1 or x0 + 20, y1=y1 or y0 + 10)


def test_cluster_by_y_groups_same_line_and_sorts_by_x():
    words = [
        _word("b", 50, 100),
        _word("a", 10, 101),  # same line as "b" (within tolerance), earlier x
        _word("c", 10, 200),  # a different line entirely
    ]
    lines = cluster_by_y(words, y_tolerance=2.5)
    assert len(lines) == 2
    assert [w.text for w in lines[0]] == ["a", "b"]
    assert [w.text for w in lines[1]] == ["c"]


def test_classify_transaction_row():
    row = DetectedRow(
        page=1,
        y0=100,
        y1=110,
        cells={
            "date": [_word("10/OCT", 10, 100)],
            "description": [_word("SPEI", 60, 100)],
            "debit": [_word("450.00", 300, 100)],
        },
        raw_words=[_word("10/OCT", 10, 100), _word("SPEI", 60, 100), _word("450.00", 300, 100)],
    )
    result = classify_row(row, headers=[], prev=None, page_width=600)
    assert result.row_type == RowType.TRANSACTION


def test_classify_continuation_row_after_transaction():
    prev = ClassifiedRow(row=None, row_type=RowType.TRANSACTION, confidence=0.9)
    row = DetectedRow(
        page=1,
        y0=112,
        y1=122,
        cells={"description": [_word("Referencia 123", 60, 112, 160, 122)]},
        raw_words=[_word("Referencia 123", 60, 112, 160, 122)],
    )
    result = classify_row(row, headers=[], prev=prev, page_width=600)
    assert result.row_type == RowType.CONTINUATION


def test_classify_repeated_header_row():
    header = HeaderCandidate(page=2, y0=48, y1=62, column_anchors={"date": 50, "balance": 500})
    row = DetectedRow(page=2, y0=50, y1=60, cells={}, raw_words=[_word("FECHA", 10, 50)])
    result = classify_row(row, headers=[header], prev=None, page_width=600)
    assert result.row_type == RowType.REPEATED_HEADER


def test_classify_wide_footer_row():
    words = [_word(f"w{i}", x, 700) for i, x in enumerate(range(0, 580, 40))]
    row = DetectedRow(page=1, y0=700, y1=710, cells={}, raw_words=words)
    result = classify_row(row, headers=[], prev=None, page_width=600)
    assert result.row_type == RowType.FOOTER


def test_classify_partial_match_is_unknown():
    row = DetectedRow(
        page=1,
        y0=100,
        y1=110,
        cells={"date": [_word("10/OCT", 10, 100)]},
        raw_words=[_word("10/OCT", 10, 100)],
    )
    result = classify_row(row, headers=[], prev=None, page_width=600)
    assert result.row_type == RowType.UNKNOWN
