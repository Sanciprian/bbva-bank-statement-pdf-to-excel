"""Best-effort Camelot table extraction (doc section 24).

Camelot is an assistant, never a hard dependency: every failure mode here
(missing dependency, no tables found, a parsing exception) degrades to an
empty list rather than propagating, so `StatementParser.parse()` can never
fail because Camelot failed. The research harness (scripts/research_harness.py)
showed Camelot fragmenting BBVA statements into many overlapping, inconsistent
candidate tables -- it is used here for diagnostics/corroboration only, not as
the structural source of truth.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class CandidateTable:
    page: int
    dataframe: "pd.DataFrame"
    accuracy: float
    whitespace: float
    flavor: str


def extract_tables(path: Path, pages: str = "all") -> list[CandidateTable]:
    try:
        import camelot
    except Exception:
        return []

    candidates: list[CandidateTable] = []
    for flavor in ("lattice", "stream"):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                tables = camelot.read_pdf(str(path), pages=pages, flavor=flavor)
        except Exception:
            continue
        for table in tables:
            report = table.parsing_report
            candidates.append(
                CandidateTable(
                    page=table.page,
                    dataframe=table.df,
                    accuracy=report.get("accuracy", 0.0),
                    whitespace=report.get("whitespace", 0.0),
                    flavor=flavor,
                )
            )
    return candidates
