"""Baseline purchased energy per fuel (kWh/year) with its source.

Priority: user reading (user_provided) > modelled energy (only when use_model and configs/model_switch.json says the model
beat the benchmark; default off) > NEED population benchmark. Missing stays None with a status, never 0.
"""
from __future__ import annotations

from typing import Optional

from .. import config
from ..schemas.enums import Provenance
from ..schemas.property import HomeRecord
from ..schemas.scenario import Baseline, UserReading
from .units import electric_heating_share

BLOCKING_FLAGS = {
    "flag_conflict_gas_heating_no_mains_gas": "gas boiler recorded but no mains gas",
    "flag_energy_zero_or_negative": "EPC energy zero or negative (net-zero home)",
    "flag_no_heating_description": "no usable main heating description",
}


def model_enabled() -> bool:
    sw = config.model_switch()
    return bool(sw and sw.get("use_model_baseline") and sw.get("beat_benchmark"))


def get_baseline(home: HomeRecord, user_reading: Optional[UserReading] = None, use_model: bool = False) -> Baseline:
    notes = []
    gas, gas_prov, gas_status = home.baseline_gas_kwh, home.provenance.get("baseline_gas_kwh", Provenance.unavailable), home.gas_status or "unknown"
    elec, elec_prov, elec_status = home.baseline_elec_kwh, home.provenance.get("baseline_elec_kwh", Provenance.unavailable), home.elec_status or "unknown"
    if gas is None:
        gas_prov = Provenance.unavailable
    if elec is None:
        elec_prov = Provenance.unavailable

    if use_model:
        notes.append("modelled baseline requested; " + ("enabled by switch file but no model output is wired in this engine version, benchmark used"
                                                       if model_enabled() else "switch file absent or model did not beat the benchmark, benchmark used"))
    if user_reading is not None:
        if user_reading.gas_kwh is not None:
            gas, gas_prov, gas_status = float(user_reading.gas_kwh), Provenance.user_provided, "user_provided"
        if user_reading.elec_kwh is not None:
            elec, elec_prov, elec_status = float(user_reading.elec_kwh), Provenance.user_provided, "user_provided"

    provs = {gas_prov, elec_prov}
    if gas is None and elec is None:
        source = "unavailable"
    elif provs == {Provenance.user_provided}:
        source = "user_provided"
    elif Provenance.user_provided in provs:
        source = "mixed"
    else:
        source = "population_benchmark"

    blocking = [k for k in BLOCKING_FLAGS if getattr(home, k)]
    gas_heated = home.heating_type == "gas_boiler" and gas is not None and gas > 0 and not home.flag_conflict_gas_heating_no_mains_gas
    share, share_src = electric_heating_share(home)
    elec_heated = share is not None and not gas_heated and elec is not None and elec > 0 and not blocking
    if elec_heated:
        notes.append(f"electric heating: {share:.0%} of electricity treated as space + water heating ({share_src}, D16)")
    elif home.heating_type in ("electric",):
        notes.append(f"electric heating savings not estimated: {share_src}")
    if Provenance.population_benchmark in provs:
        notes.append("NEED benchmark: median of similar homes in the region, not this home's meter (D6)")
    if gas is None or elec is None:
        notes.append("baseline " + " and ".join(f for f, v in (("gas", gas), ("electricity", elec)) if v is None) + " unavailable")
    return Baseline(gas_kwh=gas, elec_kwh=elec, gas_provenance=gas_prov, elec_provenance=elec_prov,
                    gas_status=gas_status, elec_status=elec_status, source=source, blocking_flags=blocking,
                    gas_heated=gas_heated, elec_heated=elec_heated, elec_heat_share=share if elec_heated else None,
                    elec_heat_share_source=share_src if elec_heated else "", note="; ".join(notes))


def blocking_reasons(b: Baseline) -> list[str]:
    return [BLOCKING_FLAGS[f] for f in b.blocking_flags]
