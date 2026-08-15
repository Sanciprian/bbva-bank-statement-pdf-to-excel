"""Phase-0 research harness: dump PyMuPDF word geometry and camelot's output
for every PDF in a directory, so the header/column/row detection heuristics
in `bank_parser` can be designed against real evidence instead of guesses.

Usage:
    python scripts/research_harness.py [--input input] [--output-dir output/research]

For each PDF this prints page dimensions and a word/table count summary to
the console, and writes the full per-word geometry to a JSON file per PDF
(gitignored, under output/) for closer inspection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf


def dump_words(pdf_path: Path) -> dict:
    doc = pymupdf.open(pdf_path)
    pages = []
    for page_index in range(doc.page_count):
        page = doc[page_index]
        words = page.get_text("words")  # (x0, y0, x1, y1, text, block_no, line_no, word_no)
        pages.append(
            {
                "page_number": page_index + 1,
                "width": page.rect.width,
                "height": page.rect.height,
                "rotation": page.rotation,
                "word_count": len(words),
                "words": [
                    {
                        "text": w[4],
                        "x0": w[0],
                        "y0": w[1],
                        "x1": w[2],
                        "y1": w[3],
                        "block": w[5],
                        "line": w[6],
                        "word_no": w[7],
                    }
                    for w in words
                ],
            }
        )
    doc.close()
    return {"filename": pdf_path.name, "page_count": len(pages), "pages": pages}


def run_camelot(pdf_path: Path) -> list[dict]:
    try:
        import camelot
    except Exception as exc:  # pragma: no cover - diagnostic only
        return [{"error": f"camelot unavailable: {exc}"}]

    results = []
    for flavor in ("lattice", "stream"):
        try:
            tables = camelot.read_pdf(str(pdf_path), pages="all", flavor=flavor)
        except Exception as exc:  # pragma: no cover - diagnostic only
            results.append({"flavor": flavor, "error": str(exc)})
            continue
        for table in tables:
            results.append(
                {
                    "flavor": flavor,
                    "page": table.page,
                    "shape": list(table.shape),
                    "accuracy": table.parsing_report.get("accuracy"),
                    "whitespace": table.parsing_report.get("whitespace"),
                }
            )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="input", help="Directory of PDFs to inspect.")
    parser.add_argument(
        "--output-dir", default="output/research", help="Where to write per-PDF word-geometry JSON."
    )
    args = parser.parse_args(argv)

    input_dir = Path(args.input)
    output_dir = Path(args.output_dir)
    pdfs = sorted(input_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {input_dir}/", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    for pdf_path in pdfs:
        print(f"\n=== {pdf_path.name} ===")
        geometry = dump_words(pdf_path)
        for page in geometry["pages"]:
            print(
                f"  page {page['page_number']}: "
                f"{page['width']:.0f}x{page['height']:.0f}pt, "
                f"rotation={page['rotation']}, words={page['word_count']}"
            )
        dump_path = output_dir / f"{pdf_path.stem}.words.json"
        dump_path.write_text(json.dumps(geometry, indent=2, ensure_ascii=False))
        print(f"  wrote {dump_path}")

        camelot_results = run_camelot(pdf_path)
        if camelot_results and "error" in camelot_results[0]:
            print(f"  camelot: {camelot_results[0]['error']}")
        else:
            print(f"  camelot: {len(camelot_results)} candidate table(s) found")
            for table in camelot_results:
                if "error" in table:
                    print(f"    [{table['flavor']}] error: {table['error']}")
                else:
                    print(
                        f"    [{table['flavor']}] page {table['page']}: "
                        f"shape={table['shape']} accuracy={table['accuracy']} "
                        f"whitespace={table['whitespace']}"
                    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
