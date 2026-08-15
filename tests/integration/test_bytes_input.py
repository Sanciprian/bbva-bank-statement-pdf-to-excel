"""Covers the in-memory (bytes) input path a UI like Streamlit relies on --
no temporary file should ever need to touch disk."""

import io

from bank_parser import StatementParser


def test_parse_from_bytes_matches_parse_from_path(real_pdfs):
    pdf_path = real_pdfs[0]
    parser = StatementParser()

    from_path = parser.parse(pdf_path)
    from_bytes = parser.parse(pdf_path.read_bytes(), filename=pdf_path.name)

    assert from_bytes.source_filename == from_path.source_filename
    assert len(from_bytes.transactions) == len(from_path.transactions)
    assert from_bytes.validation.is_reliable == from_path.validation.is_reliable


def test_export_to_in_memory_buffers(real_pdfs):
    statement = StatementParser().parse(real_pdfs[0])

    excel_buffer = io.BytesIO()
    statement.to_excel(excel_buffer)
    assert excel_buffer.tell() > 0

    csv_buffer = io.StringIO()
    statement.to_csv(csv_buffer)
    assert len(csv_buffer.getvalue()) > 0
