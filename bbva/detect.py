"""Detect which BBVA statement format a PDF uses."""

from __future__ import annotations

import pdfplumber

from . import models


def detect_format(pdf: "pdfplumber.PDF") -> str:
    """Return ``models.DEBIT`` or ``models.CREDIT_REGULAR`` (used as a format flag).

    Credit-card statements contain "DESGLOSE DE MOVIMIENTOS"; debit/checking
    statements contain "Detalle de Movimientos Realizados".
    """
    # Only the first few pages are needed to tell the formats apart.
    head = "\n".join((page.extract_text() or "") for page in pdf.pages[:4])
    upper = head.upper()
    if "DESGLOSE DE MOVIMIENTOS" in upper or "CARGOS,COMPRAS Y ABONOS REGULARES" in upper:
        return models.CREDIT_REGULAR
    if "DETALLE DE MOVIMIENTOS REALIZADOS" in upper:
        return models.DEBIT
    # Fall back to credit if the card-only "PAGO PARA NO GENERAR INTERESES" marker shows.
    if "PAGO PARA NO GENERAR INTERESES" in upper:
        return models.CREDIT_REGULAR
    return models.DEBIT
