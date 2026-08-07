"""Optional spending categorization using a local LLM via Ollama.

Extraction is fully deterministic; the LLM is used *only* to label each unique
merchant with a spending category. Results are cached on disk (keyed by normalized
description) so repeated runs don't re-query the model. If Ollama is unreachable the
categorizer degrades gracefully: every row gets ``"uncategorized"`` and a warning is
printed, so the Excel file is still produced.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List

import requests

from .models import Transaction

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:7b"

CATEGORIES = [
    "groceries", "restaurants", "income", "transfer", "rent", "utilities",
    "fees", "shopping", "travel", "healthcare", "entertainment", "unknown",
]

_PROMPT = """You categorize bank-statement transactions for a person in Mexico.

Reply with ONLY one word, the category, nothing else. Choose exactly one of:
{cats}

Transaction description: "{desc}"
Category:"""

# Cheap deterministic hints applied before asking the model (saves queries and fixes
# the obvious Spanish-specific cases the model sometimes misses).
_RULES = [
    (r"SPEI|TRASPASO|TRANSFER|ENVIADO|RECIBIDO", "transfer"),
    (r"PAGO BECAS|NOMINA|DEPOSITO|ABONO", "income"),
    (r"OXXO|7\s?ELEV|7 ELEVEN|SUPER|WALMART|SORIANA|HEB|COSTCO", "groceries"),
    (r"REST|TACO|CAFE|STARBUCKS|BAR |PIZZA|BURGER|SUSHI|COCINA|FOOD|BPK", "restaurants"),
    (r"CINEPOLIS|CINEMEX|SPOTIFY|NETFLIX|CINE", "entertainment"),
    (r"UBER|DIDI|CABIFY|VIATOR|AEROMEXICO|VIVA|VOLARIS|HOTEL|MOTEL", "travel"),
    (r"FARMACIA|HOSPITAL|MEDIC|DENTAL|CLINICA", "healthcare"),
    (r"CFE|TELMEX|IZZI|TOTALPLAY|AGUA|GAS NATURAL|COMISION", "utilities"),
]


def normalize(desc: str) -> str:
    return re.sub(r"\s+", " ", (desc or "").strip().upper())


def _rule_category(desc: str):
    up = normalize(desc)
    for pattern, cat in _RULES:
        if re.search(pattern, up):
            return cat
    return None


def categorize(
    transactions: Iterable[Transaction],
    *,
    model: str = DEFAULT_MODEL,
    cache_path: Path | None = None,
    use_llm: bool = True,
) -> None:
    """Assign ``category`` to every transaction in place."""
    txns: List[Transaction] = list(transactions)
    cache: Dict[str, str] = _load_cache(cache_path)
    llm_available = use_llm

    for tx in txns:
        key = normalize(tx.description)
        if not key:
            tx.category = "unknown"
            continue
        if key in cache:
            tx.category = cache[key]
            continue

        cat = _rule_category(key)
        if cat is None and llm_available:
            cat = _ask_ollama(key, model)
            if cat is None:  # Ollama failed -> stop trying, fall back.
                llm_available = False
        if cat is None:
            cat = "uncategorized" if use_llm else "unknown"
        cache[key] = cat
        tx.category = cat

    if use_llm and not llm_available:
        print(
            "  [warn] Ollama unavailable - rows without a rule match left "
            "'uncategorized'. Start Ollama or run with --no-llm to silence this."
        )
    _save_cache(cache_path, cache)


def _ask_ollama(desc: str, model: str):
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": _PROMPT.format(cats=", ".join(CATEGORIES), desc=desc),
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip().lower()
    except Exception:
        return None
    for cat in CATEGORIES:
        if cat in text:
            return cat
    return "unknown"


def _load_cache(path: Path | None) -> Dict[str, str]:
    if path and path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(path: Path | None, cache: Dict[str, str]) -> None:
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
