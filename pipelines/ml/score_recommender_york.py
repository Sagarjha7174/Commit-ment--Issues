"""M5: assessor-relevance probability for every York home -> data/processed/region=york/recommender_scores.parquet.

Columns: property_id, p_<measure> (null when the engine rule says infeasible or no model/table is available).
Usage: .venv/bin/python pipelines/ml/score_recommender_york.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import YORK  # noqa: E402
from backend.app.data.loaders import homes_frame  # noqa: E402
from backend.app.ml import features as F, registry  # noqa: E402
from backend.app.schemas.enums import MEASURE_ORDER, FeasibilityState  # noqa: E402
from backend.app.schemas.property import home_from_row  # noqa: E402
from backend.app.services.feasibility import assess  # noqa: E402
from backend.app.services.recommender import probability  # noqa: E402

OUT = YORK / "recommender_scores.parquet"


def score_all() -> pd.DataFrame:
    homes = [home_from_row(r) for r in homes_frame().to_dict("records")]
    rows = [F.features(F.state_from_home(h), "recommender") for h in homes]
    feas = [{i.measure: i.state for i in assess(h)} for h in homes]
    out = pd.DataFrame({"property_id": [h.home_id for h in homes]})
    for m in MEASURE_ORDER:
        model = registry.get(f"rec_{m.value}")
        if model is not None:   # batch predict, same calibration as the service
            iso = model.meta["isotonic"]
            p = np.interp(model.predict(rows), iso["x"], iso["y"])
        else:
            p = np.array([probability(h, m)[0] for h in homes], dtype=float)
        ok = np.array([f[m] != FeasibilityState.infeasible for f in feas])
        out[f"p_{m.value}"] = np.where(ok, p, np.nan)
    return out


if __name__ == "__main__":
    df = score_all()
    df.to_parquet(OUT, index=False)
    print(f"wrote {OUT} ({len(df):,} homes); non-null per measure: "
          + ", ".join(f"{c}={df[c].notna().sum():,}" for c in df.columns if c.startswith("p_")))
