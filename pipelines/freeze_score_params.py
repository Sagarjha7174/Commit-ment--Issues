"""Freeze energy-intensity p10/p90 (TRAIN split only) into configs/score_params.json.

intensity = (baseline_gas_kwh + baseline_elec_kwh) / floor_area_m2   [kWh/m2/yr, population benchmark]
When configs/engine_calibration.json holds an area elasticity (D21), the baselines are first scaled within their
floor-area band exactly as the engine does (backend/app/services/baseline.area_factor) and the version becomes v2.
Exclusions are applied in order and each is counted once (first matching reason).
Never recompute these elsewhere: read configs/score_params.json.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = ROOT / "data/processed/region=york/homes_tagged.parquet"
OUT = ROOT / "configs/score_params.json"
VERSION = "score-params-v1"


def scaled_baselines(h: pd.DataFrame) -> tuple[pd.Series, pd.Series, bool]:
    """Apply the engine's within-band area scaling (D21) when calibrated; returns (gas, elec, scaled?)."""
    from backend.app import config
    from backend.app.services.baseline import area_factor
    cal = config.engine_calibration()
    if not (cal and cal.get("area_elasticity")):
        return h.baseline_gas_kwh, h.baseline_elec_kwh, False
    def f(fuel, prov_col):
        return h.apply(lambda r: area_factor(fuel, r.floor_area_m2, r.benchmark_cell_level, cal)[0]
                       if r[prov_col] == "population_benchmark" and not r.flag_floor_area_implausible else 1.0, axis=1)
    return h.baseline_gas_kwh * f("gas", "prov_baseline_gas_kwh"), h.baseline_elec_kwh * f("elec", "prov_baseline_elec_kwh"), True


def exclusion_reason(h: pd.DataFrame) -> pd.Series:
    reasons = [
        ("energy_zero_or_negative_A_rated", h.epc_predicted_consumption_status.eq("observed_net_zero_or_negative")),
        ("gas_boiler_but_no_mains_gas", h.flag_conflict_gas_heating_no_mains_gas.astype(bool)),
        ("no_heating_description", h.flag_missing_heating.astype(bool)),
        ("floor_area_missing", h.floor_area_m2.isna()),
        ("floor_area_implausible", h.flag_floor_area_implausible.astype(bool)),
        ("baseline_gas_unavailable", h.baseline_gas_kwh.isna()),
        ("baseline_elec_unavailable", h.baseline_elec_kwh.isna()),
    ]
    out = pd.Series(None, index=h.index, dtype=object)
    for name, cond in reasons:
        out[out.isna() & cond.fillna(False).to_numpy()] = name
    return out


def main():
    h = pd.read_parquet(SRC)
    tr = h[h.split == "train"].copy()
    tr["reason"] = exclusion_reason(tr)
    tr["baseline_gas_kwh"], tr["baseline_elec_kwh"], scaled = scaled_baselines(tr)
    used = tr[tr.reason.isna()]
    inten = (used.baseline_gas_kwh + used.baseline_elec_kwh) / used.floor_area_m2
    assert np.isfinite(inten).all() and (inten > 0).all()
    params = {
        "version": "score-params-v2" if scaled else VERSION,
        "area_scaled_baselines": scaled,
        "intensity": {
            "definition": "(baseline_gas_kwh + baseline_elec_kwh) / floor_area_m2",
            "units": "kWh per m2 per year (population benchmark energy, not metered)",
            "p10": round(float(np.percentile(inten, 10)), 3),
            "p90": round(float(np.percentile(inten, 90)), 3),
            "median": round(float(np.median(inten)), 3),
            "n": int(len(inten)),
            "n_train_total": int(len(tr)),
            "n_excluded": int(tr.reason.notna().sum()),
            "excluded_by_reason": {k: int(v) for k, v in tr.reason.value_counts().sort_index().items()},
            "percentile_method": "numpy.percentile, linear interpolation",
        },
        "split": "train",
        "source_file": str(SRC.relative_to(ROOT)),
        "date": date.today().isoformat(),
        "note": "Baselines are NEED population benchmarks, so intensity reflects home type/rating/size cells, not individual metering.",
    }
    OUT.write_text(json.dumps(params, indent=1))
    print(json.dumps(params, indent=1))


if __name__ == "__main__":
    main()
