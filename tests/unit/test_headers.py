from bank_parser.detection.headers import find_header_candidates
from bank_parser.models.document import DocumentWord, SpatialDocument, SpatialPage


def _word(text, x0, y0, x1, y1):
    return DocumentWord(text=text, page=1, x0=x0, y0=y0, x1=x1, y1=y1)


def _document(words):
    page = SpatialPage(page_number=1, width=600, height=800, words=words)
    return SpatialDocument(pages=[page], source_filename="synthetic.pdf")


def test_finds_two_line_spanish_header():
    words = [
        _word("FECHA", 10, 100, 40, 110),
        _word("SALDO", 400, 100, 430, 110),
        _word("DESCRIPCION", 60, 112, 140, 122),
        _word("CARGOS", 300, 112, 340, 122),
        _word("ABONOS", 350, 112, 390, 122),
    ]
    candidates = find_header_candidates(_document(words))
    assert len(candidates) == 1
    candidate = candidates[0]
    assert {"date", "description", "debit", "credit", "balance"} <= set(candidate.column_anchors)
    assert candidate.y0 == 100
    assert candidate.y1 == 122


def test_finds_english_single_line_header():
    words = [
        _word("DATE", 10, 100, 40, 110),
        _word("DESCRIPTION", 60, 100, 140, 110),
        _word("WITHDRAWAL", 300, 100, 360, 110),
        _word("DEPOSIT", 380, 100, 430, 110),
        _word("BALANCE", 450, 100, 500, 110),
    ]
    candidates = find_header_candidates(_document(words))
    assert len(candidates) == 1
    assert set(candidates[0].column_anchors) == {"date", "description", "debit", "credit", "balance"}


def test_ignores_non_header_paragraph():
    words = [
        _word("This", 10, 100, 30, 110),
        _word("is", 35, 100, 45, 110),
        _word("just", 50, 100, 70, 110),
        _word("text", 75, 100, 95, 110),
    ]
    assert find_header_candidates(_document(words)) == []


def test_ignores_totals_summary_line():
    """A "TOTAL IMPORTE CARGOS 123.45" style line matches several
    amount-shaped categories but has no date/description -- must not be
    mistaken for a transaction-table header."""
    words = [
        _word("TOTAL", 10, 100, 40, 110),
        _word("IMPORTE", 45, 100, 90, 110),
        _word("CARGOS", 95, 100, 140, 110),
        _word("123.45", 145, 100, 190, 110),
    ]
    assert find_header_candidates(_document(words)) == []
