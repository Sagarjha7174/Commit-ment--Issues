"""M2 counterfactual pairs: consecutive certificates of the same home where the dwelling is the same but an element
changed -> data/processed/region=york/ml_epc_pairs.parquet.

Kept when (a) property type, built form and age band are unchanged, (b) floor area changed by < 5%, (c) at least one
element changed: roof (rating or loft mm), walls (rating or insulation level), glazing, heating (type, family or
rating), controls, PV. Both certificates need a SAP score in 1-110. Every split is written (the split column says
which); train pairs give the Δ0 baseline, val pairs are scored in M2 and test pairs only in M7.

Usage: .venv/bin/python pipelines/ml/build_epc_pairs.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import EPC_PAIRS, cert_features  # noqa: E402

ELEMENT_COLS = {
    "loft": ("roof_ord", "loft_mm"),
    "walls": ("walls_ord", "wall_ins_level"),
    "glazing": ("glazing_ord",),
    "heating": ("heating_ord",),
    "controls": ("controls_ord",),
    "pv": ("solar_pv",),
}
MEASURE_TYPES = tuple(ELEMENT_COLS)


def _changed(a: pd.Series, b: pd.Series) -> pd.Series:
    return a.notna() & b.notna() & (a != b)


def _up(a: pd.Series, b: pd.Series) -> pd.Series:
    return a.notna() & b.notna() & (b > a)


def build_pairs(cf: pd.DataFrame) -> pd.DataFrame:
    cf = cf.sort_values(["property_id", "cert_seq"])
    old = cf.groupby("property_id").shift(0)
    new = cf.groupby("property_id").shift(-1)
    keep = new.certificate_number.notna()
    o, n = cf[keep].reset_index(drop=True), new[keep].reset_index(drop=True)
    same = lambda c: (o[c].fillna("<na>") == n[c].fillna("<na>"))  # noqa: E731
    area_ok = (o.floor_area_m2 > 0) & (n.floor_area_m2 > 0) & ((n.floor_area_m2 / o.floor_area_m2 - 1).abs() < 0.05)
    sap_ok = o.sap_target.between(1, 110) & n.sap_target.between(1, 110)
    out = pd.DataFrame({"property_id": o.property_id, "split": o.split, "cert_old": o.certificate_number,
                        "cert_new": n.certificate_number, "sap_old": o.sap_target, "sap_new": n.sap_target,
                        "year_new": n.lodgement_date.dt.year, "year_old": o.lodgement_date.dt.year})
    for m, cols in ELEMENT_COLS.items():
        ch = np.zeros(len(o), dtype=bool)
        up = np.zeros(len(o), dtype=bool)
        for c in cols:
            ch |= _changed(o[c], n[c]).to_numpy()
            up |= _up(o[c], n[c]).to_numpy()
        if m == "heating":
            fam = _changed(o.heating_family, n.heating_family) | _changed(o.heating_type_raw, n.heating_type_raw)
            ch |= fam.to_numpy()
            up |= fam.to_numpy()    # a heating system change counts as a heating measure
        out[f"chg_{m}"] = ch
        out[f"up_{m}"] = up
    any_change = out[[f"chg_{m}" for m in MEASURE_TYPES]].any(axis=1)
    mask = same("property_type_raw") & same("built_form_raw") & same("age_band_raw") & area_ok & sap_ok & any_change
    out = out[mask.to_numpy()].reset_index(drop=True)
    out["delta_obs"] = out.sap_new - out.sap_old
    out["key"] = out.apply(lambda r: "|".join(f"{m}{'+' if r[f'up_{m}'] else '~'}" for m in MEASURE_TYPES
                                              if r[f"chg_{m}"]), axis=1)
    return out


if __name__ == "__main__":
    pairs = build_pairs(cert_features())
    pairs.to_parquet(EPC_PAIRS, index=False)
    print(f"wrote {len(pairs):,} pairs; by split {pairs.split.value_counts().to_dict()}")
    for m in MEASURE_TYPES:
        print(f"  {m:9s} changed {pairs[f'chg_{m}'].sum():6,}  upgraded {pairs[f'up_{m}'].sum():6,}")
