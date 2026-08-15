from __future__ import annotations

from pathlib import Path
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def write_csv(df: "pd.DataFrame", target: str | Path | IO[bytes]) -> None:
    """`target` is a filesystem path, or a writable file-like object (e.g. an
    in-memory `io.BytesIO` for a UI download button, never touching disk)."""
    if isinstance(target, (str, Path)):
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=False)
