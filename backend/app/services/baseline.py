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


AREA_BAND_UPPER = (50.0, 100.0, 150.0, 200.0)   # NEED floor-area bands 1-5 (docs/data_york/mappings/need_floor_area_band.csv)


def area_band(area: Optional[float]) -> Optional[int]:
    if area is None or area <= 0:
        return None
    for i, upper in enumerate(AREA_BAND_UPPER, start=1):
        if area <= upper:
            return i
    return 5


def area_factor(fuel: str, area: Optional[float], cell_level: Optional[str], cal: Optional[dict] = None) -> tuple[float, Optional[str]]:
    """D21: scale a NEED benchmark within its floor-area band by (area / band reference area)^beta.
    Only for L1 cells (which include the area band); 1.0 when not calibrated or not applicable."""
    cal = cal if cal is not None else config.engine_calibration()
    ae = (cal or {}).get("area_elasticity")
    band = area_band(area)
    if not ae or band is None or not (cell_level or "").startswith("L1"):
        return 1.0, None
    ref = ae["band_reference_area_m2"].get(str(band))
    beta = ae.get(fuel)
    if not ref or beta is None:
        return 1.0, None
    f = (area / ref) ** beta
    return f, f"{fuel} benchmark x{f:.3f} for {area:g} m² vs band reference {ref:g} m² (beta {beta:.3f}, D21)"


def benchmark_energy(home: HomeRecord) -> tuple[Optional[float], Optional[float], list[str]]:
    """The home's tagged NEED benchmark (gas, elec) with the within-band floor-area scaling applied."""
    notes = []
    gas, elec = home.baseline_gas_kwh, home.baseline_elec_kwh
    if area_band(home.floor_area_m2) is None or home.flag_floor_area_implausible:
        return gas, elec, notes
    if gas is not None and gas > 0 and home.prov_baseline_gas_kwh == "population_benchmark":
        f, n = area_factor("gas", home.floor_area_m2, home.benchmark_cell_level)
        gas *= f
        notes += [n] if n else []
    if elec is not None and home.prov_baseline_elec_kwh == "population_benchmark":
        f, n = area_factor("elec", home.floor_area_m2, home.benchmark_cell_level)
        elec *= f
        notes += [n] if n else []
    return gas, elec, notes


def model_enabled() -> bool:
    sw = config.model_switch()
    return bool(sw and sw.get("use_model_baseline") and sw.get("beat_benchmark"))


def get_baseline(home: HomeRecord, user_reading: Optional[UserReading] = None, use_model: bool = False) -> Baseline:
    gas, elec, notes = benchmark_energy(home)
    gas_prov, gas_status = home.provenance.get("baseline_gas_kwh", Provenance.unavailable), home.gas_status or "unknown"
    elec_prov, elec_status = home.provenance.get("baseline_elec_kwh", Provenance.unavailable), home.elec_status or "unknown"
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
