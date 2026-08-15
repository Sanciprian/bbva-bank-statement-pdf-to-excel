#!/usr/bin/env python3
"""Convert BBVA Mexico bank-statement PDFs into a single Excel workbook.

Extraction is deterministic (parses the PDF text layer, no OCR / vision model). An
optional local LLM (Ollama) labels each merchant with a spending category. Every
statement is reconciled against its own printed totals, so mistakes are caught.

Usage:
    python bbva_to_excel.py                         # input/ -> output/transacciones.xlsx
    python bbva_to_excel.py --no-llm                # skip categorization
    python bbva_to_excel.py --input some/dir --output out.xlsx
    python bbva_to_excel.py --model llama3.2:latest # different Ollama model
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

import pdfplumber

from bbva import categorize, detect, excel, models, parse_credit, parse_debit


def parse_pdf(path: Path) -> models.StatementResult:
    with pdfplumber.open(path) as pdf:
        fmt = detect.detect_format(pdf)
        if fmt == models.DEBIT:
            return parse_debit.parse(pdf, path.name)
        return parse_credit.parse(pdf, path.name)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default="input", help="directory of statement PDFs (default: input)")
    parser.add_argument("--output", default="output/transacciones.xlsx", help="output .xlsx path")
    parser.add_argument("--no-llm", action="store_true", help="skip local-LLM categorization")
    parser.add_argument("--model", default=categorize.DEFAULT_MODEL, help="Ollama model for categories")
    args = parser.parse_args(argv)

    input_dir = Path(args.input)
    output_path = Path(args.output)
    pdfs = sorted(input_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {input_dir}/", file=sys.stderr)
        return 1

    results: List[models.StatementResult] = []
    print(f"Parsing {len(pdfs)} statement(s) from {input_dir}/")
    for pdf_path in pdfs:
        try:
            result = parse_pdf(pdf_path)
        except Exception as exc:  # keep going; report the failure
            print(f"  [FAIL] {pdf_path.name}: {exc}")
            continue
        results.append(result)
        flag = "OK" if result.reconciled else "MISMATCH"
        extra = f" +{len(result.installments)} installments" if result.installments else ""
        print(
            f"  [{flag:8}] {pdf_path.name}  ({result.statement_type}) "
            f"{len(result.transactions)} txns{extra}"
        )
        for failure in result.check_failures():
            print(f"             {failure}")

    if not results:
        print("Nothing extracted.", file=sys.stderr)
        return 1

    # Categorize across all statements at once (shared on-disk cache).
    all_txns = [t for r in results for t in (list(r.transactions) + list(r.installments))]
    cache_path = output_path.parent / ".categories_cache.json"
    if args.no_llm:
        for t in all_txns:
            t.category = categorize._rule_category(t.description) or "unknown"
        print("Categorization: rules only (--no-llm).")
    else:
        unique = {categorize.normalize(t.description) for t in all_txns}
        print(f"Categorizing {len(unique)} unique merchants via Ollama ({args.model})...")
        categorize.categorize(all_txns, model=args.model, cache_path=cache_path, use_llm=True)

    excel.write_workbook(results, output_path)

    n_ok = sum(1 for r in results if r.reconciled)
    print(f"\nWrote {output_path}  ({len(all_txns)} rows, {n_ok}/{len(results)} statements reconciled)")
    if n_ok != len(results):
        print("Some statements did NOT reconcile - check the 'Summary' sheet.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
