"""M4: modelled energy for every York home -> data/processed/region=york/modelled_energy.parquet (git-ignored).

Columns: property_id, gas / elec point, P10, P50, P90 (kWh/yr), provenance. Gas only for gas-heated homes; homes with
no mains gas keep an observed 0; anything not modelled stays null. Uses only shipped models.

Usage: .venv/bin/python pipelines/ml/predict_energy_york.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import YORK  # noqa: E402
from backend.app.data.loaders import homes_frame  # noqa: E402
from backend.app.ml import features as F, registry  # noqa: E402
from backend.app.schemas.property import home_from_row  # noqa: E402

OUT = YORK / "modelled_energy.parquet"


def predict_all() -> pd.DataFrame:
    homes = [home_from_row(r) for r in homes_frame().to_dict("records")]
    rows = [F.features(F.state_from_home(h), "energy_york") for h in homes]
    out = pd.DataFrame({"property_id": [h.home_id for h in homes]})
    gas_heated = np.array([r["need_main_heat_gas"] == 1.0 and h.mains_gas is not False for r, h in zip(rows, homes)])
    no_mains = np.array([h.mains_gas is False for h in homes])
    for fuel in ("gas", "elec"):
        for name, col in ((f"energy_{fuel}", f"{fuel}_point"), (f"energy_{fuel}_q10", f"{fuel}_p10"),
                          (f"energy_{fuel}_q50", f"{fuel}_p50"), (f"energy_{fuel}_q90", f"{fuel}_p90")):
            m = registry.get(name)
            v = np.exp(m.predict(rows)) if m is not None else np.full(len(rows), np.nan)
            if fuel == "gas":
                v = np.where(gas_heated, v, np.where(no_mains, 0.0, np.nan))
            out[col] = v
        q = out[[f"{fuel}_p10", f"{fuel}_p50", f"{fuel}_p90"]].to_numpy()
        out[[f"{fuel}_p10", f"{fuel}_p50", f"{fuel}_p90"]] = np.sort(q, axis=1)   # NaN rows stay NaN
    out["provenance"] = "modelled"
    out["model_versions"] = ";".join(f"{k}={v}" for k, v in sorted(registry.shipped_versions().items()) if k.startswith("energy_"))
    return out


if __name__ == "__main__":
    df = predict_all()
    df.to_parquet(OUT, index=False)
    print(f"wrote {OUT} ({len(df):,} homes); gas P50 non-null {df.gas_p50.notna().sum():,}, "
          f"elec P50 non-null {df.elec_p50.notna().sum():,}, gas point non-null {df.gas_point.notna().sum():,}")
