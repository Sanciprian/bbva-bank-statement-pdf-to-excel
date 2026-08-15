"""Per-statement debug bundle (doc section 27's "debug mode"): everything
useful for understanding why a statement parsed the way it did, dumped as
JSON. This is the seam a future UI debug panel would reuse directly.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from bank_parser.models.statement import BankStatement


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value") and hasattr(value, "name"):  # Enum members
        return value.value
    return str(value)


def dump_debug_bundle(statement: BankStatement, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_filename": statement.source_filename,
        "institution": statement.institution,
        "confidence": statement.confidence,
        "validation": asdict(statement.validation),
        "diagnostics": statement.diagnostics,
        "transactions": [asdict(t) for t in statement.transactions],
    }
    path = out_dir / f"{Path(statement.source_filename).stem}.debug.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default))
    return path
