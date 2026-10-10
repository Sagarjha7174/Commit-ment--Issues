"""Freeze energy-intensity p10/p90 (TRAIN split only) into configs/score_params.json.

intensity = (baseline_gas_kwh + baseline_elec_kwh) / floor_area_m2   [kWh/m2/yr, population benchmark]
Exclusions are applied in order and each is counted once (first matching reason).
Never recompute these elsewhere: read configs/score_params.json.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/processed/region=york/homes.parquet"
OUT = ROOT / "configs/score_params.json"
VERSION = "score-params-v1"


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
    used = tr[tr.reason.isna()]
    inten = (used.baseline_gas_kwh + used.baseline_elec_kwh) / used.floor_area_m2
    assert np.isfinite(inten).all() and (inten > 0).all()
    params = {
        "version": VERSION,
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
