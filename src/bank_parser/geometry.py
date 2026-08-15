"""Low-level word-clustering geometry shared by header, row, and region
detection. Not part of the public API -- import from detection.headers /
detection.rows instead.
"""

from __future__ import annotations

import unicodedata

from bank_parser.models.document import DocumentWord


def normalize_token(text: str) -> str:
    """Lowercase and strip accents/diacritics so header matching is
    accent-insensitive (e.g. "DESCRIPCIÓN" and "descripcion" both match)."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.strip().lower()


def cluster_by_y(words: list[DocumentWord], y_tolerance: float = 2.5) -> list[list[DocumentWord]]:
    """Group words into visual lines by vertical position. A tolerance is
    used rather than exact equality because different fonts/baselines on the
    same visual line rarely share an identical y-coordinate (doc section 13).

    Returns lines sorted top-to-bottom, each line's words sorted left-to-right.
    """
    if not words:
        return []

    ordered = sorted(words, key=lambda w: w.y_center)
    lines: list[list[DocumentWord]] = [[ordered[0]]]
    line_y = [ordered[0].y_center]

    for word in ordered[1:]:
        if abs(word.y_center - line_y[-1]) <= y_tolerance:
            lines[-1].append(word)
            # Re-anchor on the running average so small drift across a long
            # line doesn't accumulate into missing later words.
            line_y[-1] = sum(w.y_center for w in lines[-1]) / len(lines[-1])
        else:
            lines.append([word])
            line_y.append(word.y_center)

    for line in lines:
        line.sort(key=lambda w: w.x0)
    return lines


def windowed_bands(
    lines: list[list[DocumentWord]], max_lines: int = 2, gap_tolerance: float = 6.0
) -> list[list[list[DocumentWord]]]:
    """Sliding windows of 1..max_lines *consecutive* lines, each window kept
    only if the gap between its lines is small. Deliberately a sliding
    window rather than a greedy chain-merge: headers span at most a couple
    of visual lines (a super-header like "SALDO" above sub-labels
    "OPERACION"/"LIQUIDACION"), and a chain-merge would risk gluing the
    header onto the transaction rows below it whenever body-row line spacing
    is just as tight as the header's own line spacing.

    Each returned band keeps its constituent lines separate (not flattened)
    so phrase matching can stay within a single visual line."""
    bands: list[list[list[DocumentWord]]] = []
    for size in range(1, max_lines + 1):
        for start in range(len(lines) - size + 1):
            window = lines[start : start + size]
            if size > 1:
                gaps_ok = all(
                    min(w.y0 for w in window[i + 1]) - max(w.y1 for w in window[i]) <= gap_tolerance
                    for i in range(len(window) - 1)
                )
                if not gaps_ok:
                    continue
            bands.append(window)
    return bands


def flatten_band(band: list[list[DocumentWord]]) -> list[DocumentWord]:
    return [w for line in band for w in line]
