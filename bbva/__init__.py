"""BBVA Mexico bank-statement PDF -> Excel toolkit.

Deterministic extraction from the PDF text layer (no OCR / vision model needed),
with an optional local-LLM categorization pass. See ``bbva_to_excel.py`` for the CLI.
"""

__all__ = [
    "models",
    "dates",
    "detect",
    "parse_credit",
    "parse_debit",
    "categorize",
    "excel",
]
