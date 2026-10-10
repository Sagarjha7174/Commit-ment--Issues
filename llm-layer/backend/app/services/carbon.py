"""Carbon change per fuel: dC = sum_f dE_f * EF_f, with dE_f = before - after. Positive = emissions fell."""
from __future__ import annotations

from typing import Optional

from .. import config
from ..schemas.enums import ValueStatus
from ..schemas.retrofit import CarbonResult, SimResult


def factors_used() -> dict:
    ef = config.emission_factors()
    return {f: {"kg_co2e_per_kwh": v["kg_co2e_per_kwh"], "units": v["units"], "source": v["source"], "year": v["year"]}
            for f, v in ef.items()}


def emissions_kg(gas_kwh: float, elec_kwh: float, factors: Optional[dict] = None) -> float:
    ef = factors or config.emission_factors()
    return gas_kwh * ef["gas"]["kg_co2e_per_kwh"] + elec_kwh * ef["elec"]["kg_co2e_per_kwh"]


def carbon_change(sim: SimResult, factors: Optional[dict] = None) -> CarbonResult:
    ef = factors or config.emission_factors()
    if sim.status != ValueStatus.ok:
        return CarbonResult(status=ValueStatus.unavailable, reason_code=sim.reason_code, factors=factors_used())
    g, e = ef["gas"]["kg_co2e_per_kwh"], ef["elec"]["kg_co2e_per_kwh"]
    gas_kg = sim.gas_saving_kwh * g
    elec_kg = sim.elec_saving_kwh * e
    before = emissions_kg(sim.before.gas_total, sim.before.elec_import, ef)
    after = emissions_kg(sim.after.gas_total, sim.after.elec_import, ef)
    total = gas_kg + elec_kg
    return CarbonResult(status=ValueStatus.ok, gas_kg=gas_kg, elec_kg=elec_kg, total_kg=total, before_kg=before,
                        after_kg=after, saving_pct_of_baseline=(100 * total / before) if before > 0 else None,
                        factors=factors_used())
