"""BBVA Mexico hints. Only genuinely bank-specific facts live here: how to
recognize a BBVA statement, and literal fallback phrases/priorities used only
when the generic engine's own detection comes up empty (doc section 26)."""

from bank_parser.profiles.base import BankProfile

BBVA_PROFILE = BankProfile(
    bank_name="BBVA",
    identifying_phrases=[
        "BBVA",
        "DESGLOSE DE MOVIMIENTOS",
        "Detalle de Movimientos Realizados",
    ],
    parsing_hints={
        # Fallback phrases for validation.totals.find_printed_totals -- used
        # only if the generic "TOTAL near a debit/credit alias word" scan
        # finds nothing.
        "total_keywords": {
            "debit": ["TOTAL IMPORTE CARGOS", "TOTAL CARGOS"],
            "credit": ["TOTAL IMPORTE ABONOS", "TOTAL ABONOS"],
            "debit_count": ["TOTAL MOVIMIENTOS CARGOS"],
            "credit_count": ["TOTAL MOVIMIENTOS ABONOS"],
        },
        # BBVA debit statements print two balance sub-columns (SALDO
        # OPERACION / SALDO LIQUIDACION) that the generic column detector
        # merges into one "balance" column; when more than one money token
        # lands there, prefer the one that matches this priority order.
        "balance_column_priority": ["operacion", "liquidacion"],
    },
)
