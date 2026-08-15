"""Local Streamlit UI for bank_parser.

This file only renders results -- every parsing decision happens inside the
`bank_parser` package (doc section 43: keep the parser independent of the
UI). Uploaded files are parsed straight from memory (`UploadedFile.getvalue()`
-> `StatementParser.parse(bytes, filename=...)`); nothing is written to disk.

Run with: streamlit run app.py
"""

from __future__ import annotations

import io

import streamlit as st

from bank_parser.export.dataframe import statements_to_dataframe
from bank_parser.export.excel_exporter import write_excel
from bank_parser.parsing.statement_parser import StatementParser
from bank_parser.pdf.reader import UnsupportedDocumentError
from bank_parser.pdf.render import render_page_to_png

MAX_PDF_PAGES_SHOWN = 6
PDF_VIEW_HEIGHT = 600  # px -- both the PDF page column and the transaction table match this, and scroll independently within it

st.set_page_config(page_title="Bank Statement Parser", page_icon="🏦", layout="wide")

st.title("🏦 Bank Statement Parser")
st.caption(
    "Local and private: PDFs are parsed entirely on this machine and never leave it. "
    "Geometry-first extraction, checked against each statement's own printed totals."
)

uploaded_files = st.file_uploader(
    "Drop bank statement PDFs here", type="pdf", accept_multiple_files=True
)

if not uploaded_files:
    st.info("Upload one or more statement PDFs to get started.")
    st.stop()


@st.cache_resource
def _parser() -> StatementParser:
    return StatementParser()


statements = []
pdf_bytes_by_filename: dict[str, bytes] = {}
for uploaded_file in uploaded_files:
    with st.spinner(f"Parsing {uploaded_file.name}..."):
        try:
            statement = _parser().parse(uploaded_file.getvalue(), filename=uploaded_file.name)
        except UnsupportedDocumentError as exc:
            st.error(f"**{uploaded_file.name}**: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 -- one bad PDF must not break the page
            st.error(f"**{uploaded_file.name}**: failed to parse -- {exc}")
            continue
    statements.append(statement)
    pdf_bytes_by_filename[statement.source_filename] = uploaded_file.getvalue()

if not statements:
    st.warning("No statements were successfully parsed.")
    st.stop()

reliable_count = sum(1 for s in statements if s.validation.is_reliable)
total_txns = sum(len(s.transactions) for s in statements)

summary_cols = st.columns(3)
summary_cols[0].metric("Statements parsed", len(statements))
summary_cols[1].metric("Reconciled", f"{reliable_count}/{len(statements)}")
summary_cols[2].metric("Total transactions", total_txns)

show_pdf = st.checkbox("📄 Compare against the original PDF pages, side by side", value=False)

st.divider()

for statement in statements:
    validation = statement.validation
    status_icon = "✅" if validation.is_reliable else "⚠️"
    status_text = "Reconciled" if validation.is_reliable else "Review required"

    with st.expander(
        f"{status_icon} {statement.source_filename} -- "
        f"{len(statement.transactions)} transactions -- {status_text}",
        expanded=not validation.is_reliable,
    ):
        cols = st.columns(4)
        cols[0].metric("Institution", statement.institution or "Unknown")
        cols[1].metric("Transactions", len(statement.transactions))
        cols[2].metric("Confidence", f"{validation.score:.0%}")
        if validation.running_balance_checks:
            cols[3].metric(
                "Balance checks",
                f"{validation.running_balance_passes}/{validation.running_balance_checks}",
            )
        else:
            cols[3].metric("Balance checks", "n/a")

        if validation.warnings:
            st.warning("\n".join(f"- {w}" for w in validation.warnings))

        df = statement.to_dataframe()

        if not show_pdf:
            st.dataframe(df, width="stretch", hide_index=True)
        else:
            pdf_col, data_col = st.columns(2)

            with pdf_col:
                st.caption("Original PDF")
                pdf_bytes = pdf_bytes_by_filename.get(statement.source_filename)
                region_pages = statement.diagnostics.get("region_pages")
                with st.container(height=PDF_VIEW_HEIGHT, border=True):
                    if pdf_bytes and region_pages:
                        start, end = region_pages
                        end = min(end, start + MAX_PDF_PAGES_SHOWN - 1)
                        if end < region_pages[1]:
                            st.caption(
                                f"Showing pages {start}-{end} of {region_pages[0]}-{region_pages[1]}"
                            )
                        for page_number in range(start, end + 1):
                            st.image(
                                render_page_to_png(pdf_bytes, page_number),
                                caption=f"Page {page_number}",
                                width="stretch",
                            )
                    else:
                        st.caption("No page image available for this statement.")

            with data_col:
                st.caption("Extracted transactions")
                st.dataframe(df, width="stretch", height=PDF_VIEW_HEIGHT, hide_index=True)

st.divider()
st.subheader("Export")

combined_df = statements_to_dataframe(statements)
csv_bytes = combined_df.to_csv(index=False).encode("utf-8")

excel_buffer = io.BytesIO()
write_excel(statements, excel_buffer)
excel_buffer.seek(0)

download_cols = st.columns(2)
download_cols[0].download_button(
    "⬇️ Download CSV",
    csv_bytes,
    file_name="transacciones.csv",
    mime="text/csv",
    width="stretch",
)
download_cols[1].download_button(
    "⬇️ Download Excel",
    excel_buffer,
    file_name="transacciones.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    width="stretch",
)
