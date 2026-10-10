"""Annualise monthly energy readings using a seasonal pattern.

yearly = sum(available months) / sum(pattern share of those months).
A missing month is never treated as 0. More than MAX_MISSING missing months -> unavailable.
"""
from __future__ import annotations

import math

GAS_PATTERN = {1: .16, 2: .14, 3: .12, 4: .08, 5: .05, 6: .03, 7: .03, 8: .03, 9: .05, 10: .08, 11: .11, 12: .12}
ELEC_PATTERN = {1: .10, 2: .09, 3: .09, 4: .08, 5: .08, 6: .07, 7: .07, 8: .07, 9: .08, 10: .08, 11: .09, 12: .10}
MAX_MISSING = 6


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def annualise(monthly: dict[int, float | None], pattern: dict[int, float]) -> tuple[float | None, str]:
    """monthly: {month 1-12: kWh or None}; absent keys count as missing. Returns (annual kWh or None, status)."""
    assert abs(sum(pattern.values()) - 1) < 1e-9, "pattern must sum to 1"
    present = {m: float(v) for m, v in monthly.items() if m in pattern and not _missing(v)}
    n_missing = 12 - len(present)
    if n_missing > MAX_MISSING:
        return None, "unavailable"
    share = sum(pattern[m] for m in present)
    if share <= 0:
        return None, "unavailable"
    status = "complete" if n_missing == 0 else f"annualised_{n_missing}_missing"
    return sum(present.values()) / share, status
