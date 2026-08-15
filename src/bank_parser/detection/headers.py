"""Header-band detection by semantic column scoring (doc section 11).

A horizontal band containing several recognized semantic concepts (date,
description, debit/credit/amount, balance...) is strong evidence that a
transaction table starts there. This never matches on a literal bank-specific
phrase or a hardcoded coordinate -- only on the alias vocabulary in
parsing.aliases.COLUMN_ALIASES (or a profile's additional aliases).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bank_parser.geometry import (
    cluster_by_y,
    flatten_band,
    normalize_token,
    windowed_bands,
)
from bank_parser.models.document import DocumentWord, SpatialDocument
from bank_parser.parsing.aliases import COLUMN_ALIASES

# A band must match at least this many *distinct* semantic columns to be
# considered a header candidate. Tuned against real BBVA statements (debit
# headers match 5/6, credit headers match 3/6) with headroom for other
# layouts that use fewer of the six categories.
MIN_MATCHED_CATEGORIES = 3

_MAX_PHRASE_WORDS = 3


@dataclass
class HeaderCandidate:
    page: int
    y0: float
    y1: float
    column_anchors: dict[str, float]
    matched_words: dict[str, list[DocumentWord]] = field(default_factory=dict)
    score: float = 0.0


def _match_line(line: list[DocumentWord], aliases: dict[str, set[str]]) -> dict[str, list[DocumentWord]]:
    """Find the longest alias-phrase match per category within one visual
    line, using a small sliding window over tokens rather than a global
    substring search (keeps multi-word phrases anchored to real word runs)."""
    tokens = [normalize_token(w.text) for w in line]
    matches: dict[str, list[DocumentWord]] = {}
    matched_lengths: dict[str, int] = {}

    for start in range(len(tokens)):
        for length in range(min(_MAX_PHRASE_WORDS, len(tokens) - start), 0, -1):
            phrase = " ".join(tokens[start : start + length])
            if not phrase:
                continue
            for category, alias_set in aliases.items():
                if phrase in alias_set and length > matched_lengths.get(category, 0):
                    matches[category] = line[start : start + length]
                    matched_lengths[category] = length
    return matches


def _score_band(band: list[list[DocumentWord]], aliases: dict[str, set[str]]) -> dict[str, list[DocumentWord]]:
    merged: dict[str, list[DocumentWord]] = {}
    for line in band:
        for category, words in _match_line(line, aliases).items():
            if category not in merged:
                merged[category] = words
    return merged


def _suppress_overlapping(candidates: list[HeaderCandidate]) -> list[HeaderCandidate]:
    """windowed_bands() produces overlapping 1- and 2-line windows around
    every real header (e.g. the header line alone, then the header line
    combined with the sub-label line below it). Keep only the
    highest-scoring candidate per overlapping y-range, per page."""
    kept: list[HeaderCandidate] = []
    for candidate in sorted(candidates, key=lambda c: c.score, reverse=True):
        overlaps = any(
            other.page == candidate.page and candidate.y0 < other.y1 and other.y0 < candidate.y1
            for other in kept
        )
        if not overlaps:
            kept.append(candidate)
    return kept


def find_header_candidates(
    document: SpatialDocument,
    aliases: dict[str, set[str]] = COLUMN_ALIASES,
    min_matched_categories: int = MIN_MATCHED_CATEGORIES,
) -> list[HeaderCandidate]:
    """Scan every page for header bands. Returns *all* matches (not just the
    best one) sorted by (page, y0) -- later matches on subsequent pages are
    how repeated headers on multi-page statements get located (doc section
    15), and downstream column-layout selection decides which ones to trust.
    """
    candidates: list[HeaderCandidate] = []

    for page in document.pages:
        lines = cluster_by_y(page.words)

        for band in windowed_bands(lines):
            matched = _score_band(band, aliases)
            if len(matched) < min_matched_categories:
                continue
            # A summary/footer line (e.g. "TOTAL IMPORTE CARGOS 4,146.57")
            # can accidentally match several amount-shaped categories at
            # once. A real transaction-table header always carries a date
            # or a description column -- require one of those too.
            if "date" not in matched and "description" not in matched:
                continue

            words = flatten_band(band)
            anchors = {category: sum(w.x_center for w in ws) / len(ws) for category, ws in matched.items()}
            candidates.append(
                HeaderCandidate(
                    page=page.page_number,
                    y0=min(w.y0 for w in words),
                    y1=max(w.y1 for w in words),
                    column_anchors=anchors,
                    matched_words=matched,
                    score=len(matched) / len(aliases),
                )
            )

    return sorted(_suppress_overlapping(candidates), key=lambda c: (c.page, c.y0))
