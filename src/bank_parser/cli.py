"""CLI entry point: a folder of statement PDFs in, CSV/XLSX out.

Keeps the same UX shape the previous BBVA-only tool had (a per-file status
line, a final tally, a non-zero exit code when something needs attention) on
top of the new generic engine.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bank_parser.diagnostics.debug import dump_debug_bundle
from bank_parser.export.csv_exporter import write_csv
from bank_parser.export.dataframe import statements_to_dataframe
from bank_parser.export.excel_exporter import write_excel
from bank_parser.parsing.statement_parser import StatementParser
from bank_parser.pdf.reader import UnsupportedDocumentError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bank-parser", description="Parse bank-statement PDFs into CSV/XLSX, locally."
    )
    parser.add_argument("--input", default="input", help="Directory of statement PDFs (default: input)")
    parser.add_argument(
        "--output-dir", default="output", help="Where to write the workbook/CSV (default: output)"
    )
    parser.add_argument("--formats", choices=["csv", "xlsx", "both"], default="both")
    parser.add_argument(
        "--debug", action="store_true", help="Also write a per-statement diagnostics JSON bundle"
    )
    args = parser.parse_args(argv)

    input_dir = Path(args.input)
    output_dir = Path(args.output_dir)
    pdfs = sorted(input_dir.glob("*.pdf"))

    if not pdfs:
        print(f"No PDFs found in {input_dir}/", file=sys.stderr)
        return 1

    print(f"Parsing {len(pdfs)} statement(s) from {input_dir}/")

    statement_parser = StatementParser()
    statements = []
    failed = 0

    for pdf_path in pdfs:
        try:
            statement = statement_parser.parse(pdf_path)
        except UnsupportedDocumentError as exc:
            print(f"  [FAIL   ] {pdf_path.name}: {exc}")
            failed += 1
            continue
        except Exception as exc:  # noqa: BLE001 -- a bad PDF must not crash the whole batch
            print(f"  [FAIL   ] {pdf_path.name}: {exc}")
            failed += 1
            continue

        statements.append(statement)
        validation = statement.validation
        label = "OK" if validation.is_reliable else "REVIEW"
        print(
            f"  [{label:7}] {pdf_path.name}  "
            f"{len(statement.transactions)} txns  score={validation.score:.2f}"
        )
        for warning in validation.warnings[:3]:
            print(f"             {warning}")

        if args.debug:
            debug_path = dump_debug_bundle(statement, output_dir / "debug")
            print(f"             debug: {debug_path}")

    if not statements:
        print("No statements were successfully parsed.", file=sys.stderr)
        return 1

    written: list[str] = []
    if args.formats in ("csv", "both"):
        csv_path = output_dir / "transacciones.csv"
        write_csv(statements_to_dataframe(statements), csv_path)
        written.append(str(csv_path))
    if args.formats in ("xlsx", "both"):
        xlsx_path = output_dir / "transacciones.xlsx"
        write_excel(statements, xlsx_path)
        written.append(str(xlsx_path))

    reliable_count = sum(1 for s in statements if s.validation.is_reliable)
    review_count = len(statements) - reliable_count
    print(
        f"\nWrote {', '.join(written)}  "
        f"({len(statements)} parsed, {reliable_count} reconciled, "
        f"{review_count} need review, {failed} failed)"
    )
    if review_count or failed:
        print("Some statements require review -- see the Summary sheet.")

    if failed:
        return 1
    if review_count:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
