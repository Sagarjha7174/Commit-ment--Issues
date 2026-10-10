"""Add provenance columns and edge-case flags -> homes_tagged.parquet (homes.parquet is not modified).

Flags the engine reads; flagged homes get improvement_potential_status = "unavailable"
(the engine must not divide by a zero/invalid baseline for them).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
YORK = ROOT / "data/processed/region=york"
AS_OF = pd.Timestamp("2026-10-10")  # fixed reference date so reruns are identical
STALE_YEARS = 10

OBSERVED = ["rating", "sap_score", "potential_rating", "potential_sap", "floor_area_m2", "property_type", "built_form",
            "age_band", "walls_rating", "roof_rating", "floor_rating", "windows_rating", "glazing", "heating_type",
            "heating_rating", "solar_pv", "mains_gas", "lodgement_date"]
NEED_MAPPED = ["need_property_type", "need_age_band", "need_floor_area_band", "need_epc_band", "need_main_fuel", "need_region"]
LEVEL_ORDER = {"L1_fuel_type_epc_area": 1, "L2_fuel_type_epc": 2, "L3_fuel_epc": 3}


def main():
    h = pd.read_parquet(YORK / "homes.parquet")
    n0 = len(h)
    t = h.copy()

    # provenance
    for c in OBSERVED:
        t[f"prov_{c}"] = np.where(t[c].isna(), "unavailable", "observed")
    t["prov_controls"] = np.where(t.controls.isna(), "unavailable", "observed")
    t["prov_smart_controls"] = np.where(t.controls.isna(), "unavailable", "assumption")  # 'smart' = TTZC proxy
    t["smart_controls"] = t.controls.eq("smart").where(t.controls.notna()).astype("boolean")
    # Correctly named alias (D7): the data dictionary does not say primary vs delivered.
    # epc_predicted_consumption_kwh_m2_primary is kept for backward compatibility (deprecated).
    t["epc_modelled_energy_kwh_m2"] = t.epc_predicted_consumption_kwh_m2_primary
    t["prov_epc_modelled_energy_kwh_m2"] = np.where(t.epc_modelled_energy_kwh_m2.isna(), "unavailable", "observed")
    t["note_epc_modelled_energy_kwh_m2"] = "EPC modelled energy per m2; primary vs delivered not stated by the data dictionary"
    t["prov_epc_predicted_consumption"] = np.where(t.epc_predicted_consumption_kwh_m2_primary.isna(), "unavailable", "modelled")
    for c in NEED_MAPPED:
        t[f"prov_{c}"] = np.where(t[c].isna(), "unavailable", "population_benchmark")
    for f in ("gas", "elec"):
        t[f"prov_baseline_{f}_kwh"] = np.select(
            [t[f"baseline_{f}_kwh"].isna(), t[f"{f}_status"].eq("no_mains_gas")],
            ["unavailable", "observed"], default="population_benchmark")  # gas 0 for no mains gas follows the observed flag
    lv = lambda s: s.map(LEVEL_ORDER)  # noqa: E731
    worst = pd.concat([lv(t.gas_benchmark_level), lv(t.elec_benchmark_level)], axis=1).max(axis=1)
    t["benchmark_cell_level"] = worst.map({v: k for k, v in LEVEL_ORDER.items()})

    # flags
    t["flag_gas_boiler_no_mains_gas"] = t.flag_conflict_gas_heating_no_mains_gas.astype(bool)
    t["flag_energy_zero_or_negative"] = t.epc_predicted_consumption_status.eq("observed_net_zero_or_negative")
    t["flag_no_heating_description"] = t.flag_missing_heating.astype(bool)
    # unknown connection only where it matters: gas-heated homes evidently have a connection
    t["flag_gas_connection_unknown"] = t.gas_status.eq("unknown_mains_gas")
    t["epc_age_years"] = ((AS_OF - t.lodgement_date).dt.days / 365.25).round(2)
    t["flag_stale_epc"] = t.epc_age_years > STALE_YEARS

    warn_cols = {
        "flag_gas_boiler_no_mains_gas": "gas boiler recorded but EPC says no mains gas; gas baseline set to 0 by rule",
        "flag_energy_zero_or_negative": "EPC predicts zero or negative energy use (on-site generation)",
        "flag_no_heating_description": "no usable main heating description",
        "flag_gas_connection_unknown": "mains gas connection unknown",
        "flag_stale_epc": f"latest EPC older than {STALE_YEARS} years",
        "flag_floor_area_implausible": "floor area outside 15-1000 m2",
    }
    W = t[list(warn_cols)].to_numpy(bool)
    msgs = np.array(list(warn_cols.values()), dtype=object)
    t["data_warnings"] = [list(msgs[row]) for row in W]
    t["n_data_warnings"] = W.sum(axis=1)

    blocking = (t.flag_gas_boiler_no_mains_gas | t.flag_energy_zero_or_negative | t.flag_no_heating_description
                | t.flag_gas_connection_unknown | t.flag_floor_area_implausible.astype(bool)
                | t.baseline_gas_kwh.isna() | t.baseline_elec_kwh.isna() | t.floor_area_m2.isna())
    base_total = t.baseline_gas_kwh + t.baseline_elec_kwh
    blocking |= ~(base_total > 0)
    t["improvement_potential_status"] = np.where(blocking, "unavailable", "computable")

    # verification
    assert len(t) == n0 == 65872, len(t)
    expected = {"flag_gas_boiler_no_mains_gas": 56, "flag_energy_zero_or_negative": 144,
                "flag_no_heating_description": 55, "flag_gas_connection_unknown": 3299}
    got = {k: int(t[k].sum()) for k in expected}
    assert got == expected, got
    for c in ("baseline_gas_kwh", "baseline_elec_kwh", "floor_area_m2", "sap_score"):
        assert t[c].isna().sum() == h[c].isna().sum(), f"{c} missing count changed"
    assert (t.loc[t.baseline_gas_kwh.eq(0), "gas_status"] == "no_mains_gas").all()
    assert not t.loc[t.flag_no_heating_description, "baseline_elec_kwh"].eq(0).any()

    a, b = t.epc_modelled_energy_kwh_m2, t.epc_predicted_consumption_kwh_m2_primary
    assert ((a == b) | (a.isna() & b.isna())).all(), "alias differs from deprecated column"
    t.to_parquet(YORK / "homes_tagged.parquet", index=False)
    print("rows", len(t), "| flags", got, "| stale", int(t.flag_stale_epc.sum()),
          "| improvement_potential", t.improvement_potential_status.value_counts().to_dict(),
          "| benchmark_cell_level", t.benchmark_cell_level.value_counts(dropna=False).to_dict())


if __name__ == "__main__":
    main()
