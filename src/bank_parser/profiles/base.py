"""Bank-hint objects (doc section 26). A profile supplies hints only -- it
never becomes a separate parsing code path. The generic engine is always
responsible for the actual extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bank_parser.geometry import normalize_token
from bank_parser.models.document import SpatialDocument

_IDENTIFYING_SEARCH_PAGES = 3


@dataclass
class BankProfile:
    bank_name: str
    identifying_phrases: list[str] = field(default_factory=list)
    additional_column_aliases: dict[str, set[str]] = field(default_factory=dict)
    ignore_phrases: list[str] = field(default_factory=list)
    parsing_hints: dict[str, Any] = field(default_factory=dict)

    def matches(self, document: SpatialDocument) -> bool:
        if not self.identifying_phrases:
            return True  # the generic profile: always matches, as a fallback

        text = " ".join(
            normalize_token(w.text)
            for page in document.pages[:_IDENTIFYING_SEARCH_PAGES]
            for w in page.words
        )
        return any(normalize_token(phrase) in text for phrase in self.identifying_phrases)
