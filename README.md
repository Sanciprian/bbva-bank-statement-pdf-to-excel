# bank-statement-parser

Convert digitally generated bank-statement PDFs into a clean, structured Excel workbook (and
CSV) — accurately, locally, and without uploading your financial data anywhere.

It reads every PDF in `input/`, extracts transactions using each PDF's own text geometry (not
plain-text scraping), verifies the numbers against the totals the bank itself prints on the
statement, and writes `output/transacciones.xlsx` and `output/transacciones.csv`.

---

## Table of contents

- [Why it works this way](#why-it-works-this-way)
- [Setup](#setup)
- [Usage](#usage)
- [How the pipeline works](#how-the-pipeline-works)
- [Project layout](#project-layout)
- [Tests](#tests)
- [Troubleshooting](#troubleshooting)
- [Privacy](#privacy)

---

## Why it works this way

A PDF does not store a table as a table. It stores independent words at (x, y) coordinates on a
page. Naive text extraction throws that position away and gets the columns wrong the moment a
statement has more than one number per line.

This parser never flattens a page to plain text. Every extracted word keeps its page and bounding
box, and every later stage — finding the transaction table, figuring out its columns,
reconstructing rows, telling a transaction apart from a repeated header or a footer disclaimer —
reasons about *position*, not word order.

It is also bank-agnostic by design. Instead of a hardcoded `if bank == "BBVA": ...` branch, column
headers are matched against a vocabulary of semantic aliases (`FECHA`/`DATE`, `CARGOS`/`DEBIT`,
`SALDO`/`BALANCE`, …), and column boundaries are derived at runtime from wherever that header's
words actually sit on the page — never from a coordinate tuned to one PDF. A bank can supply a
`BankProfile` with a few *hints* (how to recognize it, a literal fallback phrase for its totals
line), but the actual parsing logic is always the same generic engine.

Finally, extraction is checked, not trusted. Every statement's running balance and printed
CARGOS/ABONOS (or DEBIT/CREDIT) totals are re-derived from the extracted transactions and compared
against what the bank itself printed. A statement that doesn't reconcile is flagged, not silently
accepted.

No OCR, no cloud APIs, no LLM — this is deterministic geometry and arithmetic. The guiding
principle: geometry first, heuristics second, financial validation always.

---

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the `bank-parser` package (editable) plus its dependencies: `pymupdf` (spatial text
extraction), `camelot-py` (optional table-extraction assistance), `pandas`, `openpyxl`, and
`pytest` for the test suite.

---

## Usage

Drop your statement PDFs into `input/`, then run:

```bash
# Default: read input/, write output/transacciones.csv and output/transacciones.xlsx
bank-parser

# Equivalent, without an editable install:
python -m bank_parser

# Only one export format
bank-parser --formats xlsx

# Different folders
bank-parser --input some/dir --output-dir report/

# Also dump a per-statement diagnostics JSON bundle (headers found, row
# classifications, printed totals, confidence components) for debugging
bank-parser --debug
```

A typical run prints a per-statement status line and a final tally:

```
Parsing 9 statement(s) from input/
  [OK     ] Estado de Cuenta - 0W9V5CFM.pdf  16 txns  score=0.96
  [OK     ] Estado de Cuenta - YEXET3QM.pdf  160 txns  score=0.80
  ...

Wrote output/transacciones.csv, output/transacciones.xlsx  (9 parsed, 9 reconciled, 0 need review, 0 failed)
```

`OK` means the statement's own arithmetic reconciled; `REVIEW` means it didn't (the workbook still
gets written, so you can inspect the offending statement on the **Summary** sheet). Exit code is
`0` when everything reconciled, `2` when at least one statement needs review, `1` if a PDF
couldn't be parsed at all or none were found.

### As a library

```python
from bank_parser import StatementParser

statement = StatementParser().parse("statement.pdf")
if statement.validation.is_reliable:
    statement.to_excel("statement.xlsx")
else:
    print(statement.validation.warnings)
```

The parser has no dependency on the CLI or any UI — the same `StatementParser` is usable from
scripts, notebooks, tests, or a future interface without modification.

---

## How the pipeline works

```
PDF
 -> PyMuPDF word extraction (text + x/y coordinates)          src/bank_parser/pdf/
 -> header/column detection (semantic aliases, not literals)  src/bank_parser/detection/
 -> row reconstruction (words -> visual rows -> columns)      src/bank_parser/detection/
 -> row classification (transaction/continuation/header/...)  src/bank_parser/detection/
 -> normalization (Decimal money, dates, signed amounts)      src/bank_parser/parsing/
 -> financial validation (balance chain, printed totals)      src/bank_parser/validation/
 -> confidence scoring                                        src/bank_parser/diagnostics/
 -> CSV / XLSX export                                         src/bank_parser/export/
```

**Header/column detection.** Each page is scanned for a horizontal band where several column
labels are recognized at once (a `date` alias, a `description` alias, `debit`/`credit`/`amount`
aliases, a `balance` alias) — this is strong, bank-agnostic evidence that a transaction table
starts there. The x-position of each matched label becomes a column anchor; column boundaries are
the midpoints between adjacent anchors.

**Row reconstruction & classification.** Words are grouped into visual rows by y-position, then
assigned to a column by x-position. Each row is classified — `TRANSACTION`, `CONTINUATION` (a
multi-line description, e.g. an SPEI reference or RFC line), `REPEATED_HEADER` (the header
reprinted on a later page), `FOOTER` (wide disclosure text), or `UNKNOWN` — using structural
evidence (has a date? has an amount? how wide is the line?), with the reasons recorded for
debugging.

**Normalization.** Money is always parsed into `decimal.Decimal`, never `float`. Dates missing a
year (common on debit/checking statements, e.g. `10/OCT`) are resolved against the statement's own
printed period, including the December→January rollover.

**Financial validation.** Every extracted transaction's running balance is checked against the
previous one plus its own signed amount. The statement's printed CARGOS/ABONOS (or DEBIT/CREDIT)
totals and movement counts are discovered generically (a "TOTAL near a recognized column alias"
scan) and cross-checked against the extracted sums. A bank profile's literal phrases are only a
fallback if that generic scan finds nothing.

---

## Project layout

```
pyproject.toml
src/bank_parser/
  models/        DocumentWord, SpatialDocument, Transaction, BankStatement, StatementValidation
  pdf/            PyMuPDF reading + best-effort Camelot assist
  detection/      header/column detection, row reconstruction, row classification
  parsing/        money/date parsing, column aliases, StatementParser (the public API)
  profiles/       BankProfile hints (BBVA today; the seam for more banks later)
  validation/     running-balance chain, printed-totals discovery, reconciliation
  export/         DataFrame / CSV / XLSX writers
  diagnostics/    confidence scoring, debug bundle dump
  cli.py          the `bank-parser` command
scripts/
  research_harness.py   dumps PyMuPDF word geometry + Camelot output for a folder of PDFs
tests/
  unit/           synthetic, fast, no PDFs required
  integration/    runs the real PDFs in input/, skipped automatically when it's empty
input/            put your PDFs here (git-ignored)
output/           generated workbook + CSV (git-ignored)
```

`StatementParser` is deliberately the only thing the CLI touches beyond exporting — a future UI
would call the exact same `parse()` method.

---

## Tests

```bash
python -m pytest tests/ -v
```

Unit tests are synthetic and always run — money/date parsing, header/column detection against
hand-built word layouts, row classification, balance-chain and totals reconciliation, export
round-tripping. Integration tests parse every real PDF in `input/` and assert full reconciliation;
they skip automatically when `input/` is empty, so the suite passes on a fresh clone with no bank
data.

---

## Troubleshooting

- **A statement shows `REVIEW`.** Check the **Summary** sheet's `warnings` column, or re-run with
  `--debug` and inspect `output/debug/<file>.debug.json` — it records which header was found,
  every row's classification and reasons, the printed totals that were discovered, and the
  confidence breakdown.
- **`No PDFs found in input/`.** Make sure your files end in `.pdf` and are in the folder passed to
  `--input` (default `input/`).
- **A layout isn't recognized at all.** Run `python scripts/research_harness.py` — it dumps every
  word's coordinates and runs Camelot for comparison, which is the fastest way to see why the
  generic header/column detection isn't finding the table.

---

## Privacy

This repository is **public**. `input/`, `output/`, `.venv/`, and `.DS_Store` are all git-ignored,
so your real statements and the generated workbook stay on your machine and never get committed.
