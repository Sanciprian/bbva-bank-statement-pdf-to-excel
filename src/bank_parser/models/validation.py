"""Financial-validation result (doc section 22.5)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StatementValidation:
    running_balance_checks: int = 0
    running_balance_passes: int = 0

    opening_closing_reconciled: bool | None = None
    debit_total_reconciled: bool | None = None
    credit_total_reconciled: bool | None = None
    movement_count_reconciled: bool | None = None

    warnings: list[str] = field(default_factory=list)
    score: float = 0.0

    @property
    def is_reliable(self) -> bool:
        """Fail-closed: a statement is reliable only when every check that
        was actually performed passed. Checks that couldn't be attempted
        (None) don't count against it, but they also don't count for it --
        see diagnostics/scoring.py for how that's reflected in `score`."""
        if self.warnings:
            return False
        if self.running_balance_checks and self.running_balance_passes != self.running_balance_checks:
            return False
        for flag in (
            self.opening_closing_reconciled,
            self.debit_total_reconciled,
            self.credit_total_reconciled,
            self.movement_count_reconciled,
        ):
            if flag is False:
                return False
        return True
