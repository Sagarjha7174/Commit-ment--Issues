"""Modelled annual energy for a York home from the NEED models (M4). Provenance modelled.

Point prediction (energy_<fuel>) is used as a baseline only when configs/model_switch.json says it beat the benchmark
and the request asks for it (baseline.get_baseline(use_model=True)). Quantile models (energy_<fuel>_q10/q50/q90) give a
per-home household spread for the Monte Carlo (D28) when shipped. Gas is modelled only for gas-heated homes; NEED
cannot be linked to York homes, so transfer to York is unproven (docs/LABELS.md 1).
"""
from __future__ import annotations

import math
from typing import Optional

from ..ml import features as F
from ..ml import registry
from ..schemas.property import HomeRecord

Z90 = 1.2815515655446004   # standard normal 0.9 quantile


def _row(home: HomeRecord) -> dict:
    return F.features(F.state_from_home(home), "energy_york")


def gas_heated(home: HomeRecord) -> bool:
    return _row(home)["need_main_heat_gas"] == 1.0 and home.mains_gas is not False


def point(home: HomeRecord, fuel: str) -> Optional[float]:
    """Point prediction kWh/yr, or None (model not shipped, or gas for a home not heated by gas)."""
    m = registry.get(f"energy_{fuel}")
    if m is None or (fuel == "gas" and not gas_heated(home)):
        return None
    return float(math.exp(m.predict([_row(home)])[0]))


def quantiles(home: HomeRecord, fuel: str) -> Optional[tuple[float, float, float]]:
    """(P10, P50, P90) kWh/yr from the quantile models (sorted, no crossing), or None."""
    ms = [registry.get(f"energy_{fuel}_q{q}") for q in (10, 50, 90)]
    if any(m is None for m in ms) or (fuel == "gas" and not gas_heated(home)):
        return None
    row = _row(home)
    vals = sorted(float(math.exp(m.predict([row])[0])) for m in ms)
    return vals[0], vals[1], vals[2]


def quantile_sigmas(home: HomeRecord) -> dict:
    """Lognormal sigma per fuel implied by the home's P10-P90: ln(P90/P10) / (2 z0.9). Empty when not available."""
    out = {}
    for fuel in ("gas", "elec"):
        q = quantiles(home, fuel)
        if q and q[0] > 0:
            out[f"{fuel}_sigma_log"] = math.log(q[2] / q[0]) / (2 * Z90)
    return out


def versions() -> dict:
    return {k: v for k, v in registry.shipped_versions().items() if k.startswith("energy_")}
