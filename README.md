# bbva-bank-statement-pdf-to-excel

Convert BBVA México bank-statement PDFs into a single, clean Excel workbook — accurately,
locally, and without uploading your financial data anywhere.

It reads every PDF in `input/`, extracts the individual transactions, optionally labels each one
with a spending category using a local LLM, verifies the numbers against the totals BBVA prints on
the statement, and writes `output/transacciones.xlsx`.

---

## Table of contents

- [Why it works this way](#why-it-works-this-way)
- [The two statement formats](#the-two-statement-formats)
- [Setup](#setup)
- [Usage](#usage)
- [How the pipeline works (step by step)](#how-the-pipeline-works-step-by-step)
  - [1. Format detection](#1-format-detection)
  - [2. Coordinate-based parsing](#2-coordinate-based-parsing)
  - [3. Date handling and year inference](#3-date-handling-and-year-inference)
  - [4. Internal-transfer filtering](#4-internal-transfer-filtering)
  - [5. Reconciliation (the correctness check)](#5-reconciliation-the-correctness-check)
  - [6. Categorization with a local LLM](#6-categorization-with-a-local-llm)
  - [7. Writing the Excel workbook](#7-writing-the-excel-workbook)
- [The output file](#the-output-file)
- [Project layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [Privacy](#privacy)

---

## Why it works this way

BBVA's PDFs are **digitally generated and contain a clean embedded text layer** — the numbers,
dates, and descriptions are real text, not scanned images. That single fact drives the whole
design:

- **Extraction is deterministic, not AI.** Every amount and date is read directly from the PDF's
  text using the exact x/y position of each word ([`pdfplumber`](https://github.com/jsvine/pdfplumber)).
  There is **no OCR and no vision model** in the extraction path. A vision LLM reading page images
  would be slower, cost money or GPU time, and — most importantly — could silently hallucinate or
  drop an amount. Reading the text layer cannot.
- **The result is checked, not trusted.** Every statement is reconciled against the totals BBVA
  itself prints (`TOTAL CARGOS` / `TOTAL ABONOS`). If our sum doesn't match BBVA's to the cent, the
  statement is flagged. On the current sample set all 7 statements reconcile exactly.
- **The LLM does only what it's good at.** A local model is used *only* to guess a spending
  category per merchant (e.g. `STARBUCKS → restaurants`). It never touches the amounts, so it can't
  corrupt your data, and the tool still runs with the LLM turned off.

---

## The two statement formats

BBVA issues two structurally different statements, and the tool auto-detects which is which:

| | Credit card | Debit / checking |
|---|---|---|
| Products | `TARJETA … BBVA` | `Libretón`, `Cuenta Digital` |
| Section title | `DESGLOSE DE MOVIMIENTOS` | `Detalle de Movimientos Realizados` |
| Date format | `24-dic-2025` (year present) | `10/OCT` (no year — inferred) |
| Direction of money | a leading `+` = charge, `-` = payment | separate **CARGOS** and **ABONOS** columns |
| Running balance | not per row | **SALDO OPERACIÓN / LIQUIDACIÓN** columns |
| Extra tables | installments (`MESES SIN INTERESES`) | — |

Both are handled by dedicated parsers (`bbva/parse_credit.py`, `bbva/parse_debit.py`) that share
the same helpers and produce the same canonical row shape.

---

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Only three direct dependencies are installed: `pdfplumber` (PDF text + coordinates), `openpyxl`
(write `.xlsx`), and `requests` (talk to the local LLM).

Categorization is **optional**. To enable it, install [Ollama](https://ollama.com) and pull a model
once:

```bash
ollama pull qwen2.5:7b
```

If you don't, just run with `--no-llm` (see below) and you'll still get a full workbook.

---

## Usage

Drop your statement PDFs into `input/`, then run:

```bash
# Default: read input/, categorize via Ollama, write output/transacciones.xlsx
python bbva_to_excel.py

# Skip the LLM entirely (no Ollama needed) — categories come from built-in rules only
python bbva_to_excel.py --no-llm

# Point at a different input folder and/or output file
python bbva_to_excel.py --input some/dir --output report.xlsx

# Use a different local model
python bbva_to_excel.py --model llama3.2:latest
```

A typical run prints a per-statement status line and a final tally:

```
Parsing 7 statement(s) from input/
  [OK      ] Estado de Cuenta - 0W9V5CFM.pdf  (debit) 16 txns
  [OK      ] Estado de Cuenta - YEXET3QM.pdf  (credit) 70 txns +22 installments
  ...
Categorizing 196 unique merchants via Ollama (qwen2.5:7b)...

Wrote output/transacciones.xlsx  (347 rows, 7/7 statements reconciled)
```

`[OK]` means the statement reconciled against BBVA's printed totals; `[MISMATCH]` means it didn't
(and the process exits non-zero so you notice). Either way the workbook is still written so you can
inspect the offending statement on the **Summary** sheet.

---

## How the pipeline works (step by step)

The CLI (`bbva_to_excel.py`) orchestrates the modules in `bbva/`. Here is exactly what happens to
each PDF.

### 1. Format detection

`bbva/detect.py` reads the text of the first few pages and looks for marker phrases
(`DESGLOSE DE MOVIMIENTOS` → credit, `Detalle de Movimientos Realizados` → debit). This decides
which parser runs.

### 2. Coordinate-based parsing

This is the heart of the tool. For each page, `pdfplumber` returns every word together with its
bounding box (`x0`, `x1`, `top`, `bottom`). The parsers (`bbva/parse_credit.py`,
`bbva/parse_debit.py`) then, with helpers in `bbva/layout.py`:

1. **Group words into visual rows** by their vertical position (`group_into_rows`, with a small
   tolerance so a date and its amount that sit a pixel apart still merge into one logical row).
2. **Assign each word to a column by its horizontal position.** This is why the tool is robust:
   - On **debit** statements, *CARGOS* and *ABONOS* look identical (both are just peso amounts) —
     the only thing that distinguishes a charge from a deposit is **which column** it's in. The
     parser reads the header row once (`CARGOS`, `ABONOS`, `OPERACIÓN`, `LIQUIDACIÓN`), computes the
     center x of each column, and assigns every amount to the nearest column center. Splitting on
     spaces (what the old code did) cannot do this reliably; positions can.
   - On **credit** statements, a single `+` or `-` token (located in the amount band, `x > 480`)
     tells charge vs. payment.
3. **Stitch multi-line records.** Debit transactions span several lines (RFC, authorization code,
   SPEI reference, counterparty name). Continuation lines — recognised because they start in the
   description column and carry no leading date — are appended to the current transaction's
   `details` field. Page headers/footers fall outside that band and are ignored.

Every parsed movement becomes a `Transaction` (`bbva/models.py`) with a single canonical shape, so
both formats flow into the same Excel columns.

### 3. Date handling and year inference

`bbva/dates.py` maps BBVA's Spanish month abbreviations (`ene, feb, … dic`) to month numbers.

- **Credit** dates already include the year, so they parse directly.
- **Debit** dates are `DD/MMM` with **no year**. The parser reads the statement period
  (`Periodo DEL 09/10/2025 AL 08/11/2025`) and picks the year that places each date inside that
  range. This correctly resolves the **December → January roll-over** (e.g. a `28/DIC` and a
  `03/ENE` on the same statement get 2025 and 2026 respectively).

### 4. Internal-transfer filtering

When you put a credit-card purchase on *meses sin intereses*, BBVA records an internal pair on the
regular table — `PROMOCION MESES S/INT` (a `+`) and `TRASPASO A MESES SIN INTERES` (an equal `-`).
They cancel to zero and are **not real spending**, so they're excluded from the output. They are,
however, still counted during reconciliation, because BBVA's printed totals include them (see next).

### 5. Reconciliation (the correctness checks)

Every statement must pass **three independent checks**, each derived from numbers BBVA itself
prints, before it is marked `OK`:

1. **Totals.** The tool sums the charges and the credits **including** the internal pairs and
   compares them to the printed totals (`TOTAL CARGOS`/`TOTAL ABONOS` on credit,
   `TOTAL IMPORTE CARGOS`/`ABONOS` on debit), to within 5 cents. If the printed totals can't be
   found at all (e.g. BBVA reworded the line), the check **fails closed** — it never passes by
   default.
2. **Movement counts** (debit). BBVA prints `TOTAL MOVIMIENTOS CARGOS n` / `ABONOS n`; the number
   of extracted charge/deposit rows must match exactly. This catches a dropped or duplicated row
   even when the amounts still happen to sum correctly.
3. **Balance chain** (debit). Each printed `SALDO OPERACIÓN` must equal the previous saldo plus
   the signed amounts of the rows in between. This is a *row-level* check: when it fails, it names
   the exact date and description where the chain broke, instead of just flagging the whole
   statement.

Any failure marks the statement `MISMATCH`, itemizes the reasons in the console and in the
Summary sheet's `check_notes` column, and exits non-zero. The totals relationship shown on the
Summary sheet is:

```
spending_out  +  internal_excluded  ==  bbva_total_cargos
```

So you can always see, per statement, how much real spending there was, how much was internal
plumbing that got removed, and that the two add up to what the bank reported.

### 6. Categorization with a local LLM

`bbva/categorize.py` assigns a `category` to each transaction:

1. A list of **fast deterministic rules** catches the obvious, Mexico-specific cases first
   (`OXXO → groceries`, `SPEI → transfer`, `CINEPOLIS → entertainment`, …).
2. Anything not caught by a rule is sent to the local **Ollama** model (`qwen2.5:7b` by default),
   one short prompt per *unique* merchant.
3. Results are cached in `output/.categories_cache.json` keyed by merchant name, so re-runs are
   instant and don't re-query the model.
4. If Ollama isn't reachable, the tool prints a warning, labels the un-matched rows
   `uncategorized`, and **still produces the workbook**. With `--no-llm` it skips step 2 entirely
   and uses rules only.

Categories are a *best-effort convenience*, not authoritative — they never affect amounts or
reconciliation.

### 7. Writing the Excel workbook

`bbva/excel.py` writes a formatted `.xlsx` with `openpyxl`: numeric money cells, real date cells, a
frozen/filterable header, sensible column widths, and color-coded reconciliation status.

---

## The output file

`output/transacciones.xlsx` has two sheets.

**`Transactions`** — one row per real movement (installment purchases included, tagged so you can
filter them):

| column | meaning |
|---|---|
| `source_file` | which PDF the row came from |
| `statement_type` | `debit`, `credit_regular`, or `credit_installment` |
| `fecha_operacion` | date the operation happened |
| `fecha_cargo` | date it posted (when the statement provides it) |
| `description` | merchant / movement description |
| `details` | extra lines: RFC, auth code, SPEI reference, counterparty, FX info |
| `money_out` | amount charged / spent (positive, else blank) |
| `money_in` | amount deposited / credited (positive, else blank) |
| `balance` | running balance (debit statements) |
| `category` | spending category |

**`Summary`** — one row per statement plus a category-totals block:

`source_file`, `type`, `period_start`, `period_end`, `txns`, `spending_out`, `spending_in`,
`internal_excluded`, `installments`, `installment_total`, `bbva_total_cargos`, `bbva_total_abonos`,
`reconciled` (color-coded **OK**/**MISMATCH**), `check_notes` (which check failed and where).

---

## Project layout

```
bbva_to_excel.py        # CLI entry point — orchestrates everything
bbva/
  detect.py             # credit vs. debit format detection
  layout.py             # word→row grouping, column bucketing, money parsing
  dates.py              # Spanish months + year inference from the period
  parse_credit.py       # credit-card statement parser
  parse_debit.py        # debit / checking statement parser
  models.py             # Transaction + StatementResult data classes, column order
  categorize.py         # rules + local-LLM categorization, with on-disk cache
  excel.py              # formatted workbook writer
tests/
  test_bbva.py          # unit tests (synthetic) + integration tests over input/
input/                  # put your PDFs here (git-ignored)
output/                 # generated workbook + category cache (git-ignored)
```

---

## Tests

```bash
python -m pytest tests/ -v
```

The unit tests use only synthetic data and always run. The integration tests parse every PDF in
`input/` and assert that all three reconciliation checks pass, that every row has a date, a
description, and exactly one of `money_out`/`money_in`, and that every date falls inside the
statement's printed period — they skip automatically when `input/` is empty, so the suite works on
a fresh clone without any bank data.

---

## Troubleshooting

- **A statement shows `MISMATCH`.** Open the **Summary** sheet: compare `spending_out + internal_excluded`
  against `bbva_total_cargos`. A mismatch usually means a transaction row wasn't parsed (e.g. an
  unusual layout). The raw amounts are still in the PDF — re-run and check that statement's rows.
- **All categories are `uncategorized`.** Ollama isn't running or the model isn't pulled. Run
  `ollama pull qwen2.5:7b` and start Ollama, or use `--no-llm` to silence the warning.
- **`No PDFs found in input/`.** Make sure your files end in `.pdf` and are in the folder passed to
  `--input` (default `input/`).
- **Categories look stale after editing rules.** Delete `output/.categories_cache.json` to force a
  fresh categorization pass.

---

## Privacy

This repository is **public**. `input/`, `output/`, `pages/`, `private_data/`, `.venv/`, and
`.DS_Store` are all git-ignored, so your real statements, the generated workbook, and the category
cache stay on your machine and never get committed. Keep them in those folders and they're safe.
