"""Discover the statement's own printed totals, generically first (doc
section 22.2-22.3): scan for a "TOTAL ... <debit|credit alias> <value>"
pattern near a recognized column-alias word, wherever it appears in the
document. A bank profile's `parsing_hints["total_keywords"]` is only
consulted as a fallback when this generic scan finds nothing -- that keeps
the discovery mechanism itself bank-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bank_parser.geometry import cluster_by_y, normalize_token
from bank_parser.models.document import DocumentWord, SpatialDocument
from bank_parser.parsing.aliases import COLUMN_ALIASES
from bank_parser.parsing.money import looks_like_money, parse_money
from bank_parser.profiles.base import BankProfile

_LOOKAHEAD = 5


@dataclass
class PrintedTotals:
    debit_total: Decimal | None = None
    credit_total: Decimal | None = None
    debit_count: int | None = None
    credit_count: int | None = None


def _category_of(token: str) -> str | None:
    if token in COLUMN_ALIASES["debit"]:
        return "debit"
    if token in COLUMN_ALIASES["credit"]:
        return "credit"
    return None


def _scan_line(line: list[DocumentWord]) -> list[tuple[str, str, DocumentWord]]:
    """Finds every "TOTAL ... <category> <value>" fragment on one visual
    line, left to right, so a line packing two totals together (e.g.
    "TOTAL IMPORTE CARGOS 4,146.57 TOTAL MOVIMIENTOS CARGOS 14") yields both."""
    found: list[tuple[str, str, DocumentWord]] = []
    consumed: set[int] = set()

    for i, word in enumerate(line):
        if normalize_token(word.text) != "total":
            continue

        window = line[i + 1 : i + 1 + _LOOKAHEAD]
        window_tokens = [normalize_token(w.text) for w in window]
        kind = "count" if "movimientos" in window_tokens else "amount"

        category = None
        category_word = None
        for w, t in zip(window, window_tokens):
            category = _category_of(t)
            if category:
                category_word = w
                break
        if category is None:
            continue

        for candidate in line:
            if candidate.x0 <= category_word.x0 or id(candidate) in consumed:
                continue
            text = candidate.text.strip()
            if kind == "amount" and looks_like_money(text):
                found.append((kind, category, candidate))
                consumed.add(id(candidate))
                break
            if kind == "count" and text.lstrip("-").isdigit():
                found.append((kind, category, candidate))
                consumed.add(id(candidate))
                break

    return found


def _generic_totals(document: SpatialDocument) -> PrintedTotals:
    totals = PrintedTotals()
    for page in document.pages:
        for line in cluster_by_y(page.words):
            for kind, category, word in _scan_line(line):
                if kind == "amount":
                    money = parse_money(word.text)
                    if money is None:
                        continue
                    if category == "debit" and totals.debit_total is None:
                        totals.debit_total = money.value
                    elif category == "credit" and totals.credit_total is None:
                        totals.credit_total = money.value
                else:
                    count = int(word.text.strip())
                    if category == "debit" and totals.debit_count is None:
                        totals.debit_count = count
                    elif category == "credit" and totals.credit_count is None:
                        totals.credit_count = count
    return totals


def _fallback_totals(document: SpatialDocument, profile: BankProfile) -> PrintedTotals:
    """Literal-phrase fallback used only for whatever the generic scan
    didn't find. Purely additive: never overrides a generic-scan result."""
    keywords = profile.parsing_hints.get("total_keywords")
    if not keywords:
        return PrintedTotals()

    full_text_lines = [
        " ".join(w.text for w in line)
        for page in document.pages
        for line in cluster_by_y(page.words)
    ]

    def _find_amount(phrases: list[str]) -> Decimal | None:
        for line in full_text_lines:
            upper = line.upper()
            for phrase in phrases:
                if phrase.upper() in upper:
                    tail = upper.split(phrase.upper(), 1)[1]
                    for token in tail.split():
                        money = parse_money(token)
                        if money:
                            return money.value
        return None

    def _find_count(phrases: list[str]) -> int | None:
        for line in full_text_lines:
            upper = line.upper()
            for phrase in phrases:
                if phrase.upper() in upper:
                    tail = upper.split(phrase.upper(), 1)[1]
                    for token in tail.split():
                        if token.strip().lstrip("-").isdigit():
                            return int(token.strip())
        return None

    return PrintedTotals(
        debit_total=_find_amount(keywords.get("debit", [])),
        credit_total=_find_amount(keywords.get("credit", [])),
        debit_count=_find_count(keywords.get("debit_count", [])),
        credit_count=_find_count(keywords.get("credit_count", [])),
    )


def find_printed_totals(document: SpatialDocument, profile: BankProfile) -> PrintedTotals:
    totals = _generic_totals(document)
    if all(
        v is not None
        for v in (totals.debit_total, totals.credit_total, totals.debit_count, totals.credit_count)
    ):
        return totals

    fallback = _fallback_totals(document, profile)
    return PrintedTotals(
        debit_total=totals.debit_total if totals.debit_total is not None else fallback.debit_total,
        credit_total=totals.credit_total if totals.credit_total is not None else fallback.credit_total,
        debit_count=totals.debit_count if totals.debit_count is not None else fallback.debit_count,
        credit_count=totals.credit_count if totals.credit_count is not None else fallback.credit_count,
    )
