"""Semantic column aliases (doc section 11).

Header/column detection matches against these normalized phrases instead of
literal bank-specific strings or hardcoded x-coordinates -- this is the piece
that makes the engine bank-agnostic. Keys are canonical semantic column
names; values are sets of normalized (lowercase, accent-stripped) header
phrases that mean that column, in Spanish and English.
"""

from __future__ import annotations

COLUMN_ALIASES: dict[str, set[str]] = {
    "date": {
        "fecha",
        "fecha operacion",
        "fecha movimiento",
        "fecha transaccion",
        "f. operacion",
        "date",
        "posting date",
        "transaction date",
    },
    "description": {
        "concepto",
        "descripcion",
        "detalle",
        "movimiento",
        "description",
        "transaction",
    },
    "debit": {
        "cargo",
        "cargos",
        "retiro",
        "retiros",
        "debit",
        "withdrawal",
        "withdrawals",
    },
    "credit": {
        "abono",
        "abonos",
        "deposito",
        "depositos",
        "credit",
        "deposit",
        "deposits",
    },
    "amount": {
        "importe",
        "monto",
        "amount",
    },
    "balance": {
        "saldo",
        "saldo operacion",
        "saldo liquidacion",
        # "operacion"/"liquidacion" alone are the two sub-column labels that
        # appear on the line below a shared "SALDO" super-header on some
        # statements (e.g. BBVA debit: SALDO / OPERACION | LIQUIDACION).
        "operacion",
        "liquidacion",
        "balance",
    },
}
