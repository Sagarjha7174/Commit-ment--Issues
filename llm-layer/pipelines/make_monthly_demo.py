"""SYNTHETIC monthly gas/electricity, generated from annual population-benchmark baselines.

Purpose: demonstrate annualisation only. Not measured data; every row has provenance="synthetic".
Homes: the 3 demo homes + 500 random TRAIN homes (seed 42) with both baselines available.
Noise: multiplicative N(1, 0.05) per month. ~7% of months removed at random (row kept, value null).
Output: data/processed/region=york/monthly_synthetic.parquet
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from annualise import ELEC_PATTERN, GAS_PATTERN, annualise

ROOT = Path(__file__).resolve().parents[1]
YORK = ROOT / "data/processed/region=york"
SEED, N_SAMPLE, NOISE_SD, MISSING_RATE = 42, 500, 0.05, 0.07


def main():
    rng = np.random.default_rng(SEED)
    t = pd.read_parquet(YORK / "homes_tagged.parquet", columns=["property_id", "split", "baseline_gas_kwh", "baseline_elec_kwh"])
    demo = [h["property_id"] for h in json.loads((ROOT / "configs/demo_homes.json").read_text())["homes"]]
    pool = t[(t.split == "train") & t.baseline_gas_kwh.notna() & t.baseline_elec_kwh.notna()].sort_values("property_id")
    sample = pool.sample(N_SAMPLE, random_state=SEED).property_id.tolist()
    ids = demo + sorted(set(sample) - set(demo))
    t = t.set_index("property_id").loc[ids]
    rows = []
    for pid, r in t.iterrows():
        for fuel, pattern, annual in (("gas", GAS_PATTERN, r.baseline_gas_kwh), ("elec", ELEC_PATTERN, r.baseline_elec_kwh)):
            for m in range(1, 13):
                if pd.isna(annual):
                    val, status = None, "baseline_unavailable"
                else:
                    val = float(annual * pattern[m] * rng.normal(1, NOISE_SD))
                    status = "present"
                    if rng.random() < MISSING_RATE:
                        val, status = None, "removed_at_random"
                rows.append({"property_id": pid, "fuel": fuel, "month": m, "kwh": val, "month_status": status,
                             "annual_baseline_kwh": None if pd.isna(annual) else float(annual), "provenance": "synthetic",
                             "is_demo_home": pid in demo})
    df = pd.DataFrame(rows)
    df.to_parquet(YORK / "monthly_synthetic.parquet", index=False)

    res = []
    for (pid, fuel), g in df.groupby(["property_id", "fuel"], sort=True):
        if g.annual_baseline_kwh.isna().all():
            continue
        est, st = annualise(dict(zip(g.month, g.kwh)), GAS_PATTERN if fuel == "gas" else ELEC_PATTERN)
        base = g.annual_baseline_kwh.iloc[0]
        res.append({"fuel": fuel, "status": st, "err_pct": None if est is None or base == 0 else 100 * (est - base) / base})
    res = pd.DataFrame(res)
    print("rows", len(df), "| homes", df.property_id.nunique(), "| removed months",
          int((df.month_status == "removed_at_random").sum()), f"({100 * (df.month_status == 'removed_at_random').mean():.1f}%)")
    print("annualise status:", res.status.value_counts().to_dict())
    print("abs error % vs baseline (median, p95):", round(res.err_pct.abs().median(), 2), round(res.err_pct.abs().quantile(.95), 2))


if __name__ == "__main__":
    main()
