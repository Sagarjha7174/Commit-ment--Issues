"""NEED-calibrated reference estimate for packages with two or more fabric/controls measures (DECISIONS D17).

The engineering (sequential multiplicative) estimate stays the headline number. Next to it, the same package is
re-simulated with every fabric/controls impact scaled by the NEED combination factor, giving the saving NEED observed
for comparable combinations. Heat pump and solar PV steps are re-run on the resulting state, so the per-fuel figures
stay reconciled.
"""
from __future__ import annotations

from typing import Optional

from .. import config
from ..schemas.enums import CombinationMode, FeasibilityState, MeasureId, ValueStatus
from ..schemas.property import HomeRecord
from ..schemas.retrofit import FeasibilityItem
from ..schemas.scenario import Assumptions, Baseline
from .carbon import carbon_change
from .simulator import FABRIC_CONTROLS, simulate

LABEL = "NEED-calibrated reference: what NEED observed for comparable combined installations (D17); not a guarantee"


def calibrated_view(baseline: Baseline, home: HomeRecord, measures: list[MeasureId], a: Assumptions,
                    feas: list[FeasibilityItem]) -> Optional[dict]:
    if a.combination_mode != CombinationMode.engineering or config.combination_calibration() is None:
        return None
    fmap = {f.measure: f for f in feas}
    active = [m for m in measures if m in FABRIC_CONTROLS and fmap[m].state != FeasibilityState.infeasible]
    if len(active) < 2:
        return None
    sim = simulate(baseline, home, measures, a.model_copy(update={"combination_mode": CombinationMode.need_calibrated}), feas)
    if sim.status != ValueStatus.ok:
        return None
    carb = carbon_change(sim)
    note = next((w for w in sim.warnings if w.startswith("NEED-calibrated")), "")
    return {"label": LABEL, "factor_note": note,
            "gas_saving_kwh": sim.gas_saving_kwh, "elec_saving_kwh": sim.elec_saving_kwh,
            "purchased_saving_kwh": sim.purchased_saving_kwh,
            "improvement_potential_pct": sim.improvement_potential_pct,
            "carbon_saving_kg": carb.total_kg, "carbon_saving_pct": carb.saving_pct_of_baseline}
