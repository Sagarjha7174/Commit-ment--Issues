"""Tiny synthetic models for ML unit tests: the tests pass without any trained model in models/."""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from backend.app.ml import features as F
from backend.app.ml import registry
from backend.app.ml.tuning import BASE_PARAMS
from tests.conftest import make_home

RATINGS = ["Very Poor", "Poor", "Average", "Good", "Very Good"]


def synthetic_homes(n: int = 600, seed: int = 0) -> list:
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        walls_ins = rng.choice(["Cavity wall, as built, no insulation (assumed)", "Cavity wall, filled cavity",
                                "Solid brick, as built, no insulation (assumed)"])
        out.append(make_home(
            home_id=f"S{i}", walls_rating=str(rng.choice(RATINGS)), roof_rating=str(rng.choice(RATINGS)),
            walls_description=str(walls_ins), roof_description=f"Pitched, {int(rng.choice([0, 50, 100, 200, 270]))} mm loft insulation",
            glazing=str(rng.choice(["single", "partial", "double"])), multi_glaze_pct=float(rng.choice([0, 40, 80, 100])),
            controls=str(rng.choice(["none", "timer", "full", "smart"])), solar_pv=bool(rng.random() < 0.2),
            pv_roof_pct=0.0, floor_area_m2=float(rng.integers(50, 200)), habitable_rooms=float(rng.integers(2, 8)),
            lodgement_date=f"{int(rng.integers(2010, 2026))}-06-01", sap_score=None,
            mainheat_description="Boiler and radiators, mains gas", main_fuel="mains gas (not community)",
            heating_rating=str(rng.choice(RATINGS[1:]))))
    return out


def synthetic_sap(h) -> float:
    d = F.derive(F.state_from_home(h))
    return (15 + 4 * d["walls_ord"] + 3 * d["roof_ord"] + 6 * d["glazing_ord"] + 2 * d["controls_ord"]
            + 6 * d["solar_pv"] + 0.02 * d["loft_mm"] + 2 * d["heating_ord"])


def train_tiny_sap(models_dir, registry_file) -> str:
    """Train + save + register a tiny monotone SAP model; returns its version."""
    homes = synthetic_homes()
    rows = [F.features(F.state_from_home(h), "sap") for h in homes]
    y = np.array([synthetic_sap(h) for h in homes])
    df = pd.DataFrame(rows)
    cols = list(F.FEATURE_SETS["sap"])
    cats = F.fit_categories(df, cols)
    X = F.to_frame(df, cols, cats)
    params = {**BASE_PARAMS, "objective": "regression", "metric": "l1", "num_leaves": 15, "min_data_in_leaf": 10,
              "learning_rate": 0.1, "monotone_constraints": F.monotone_constraints("sap"), "num_threads": 1}
    b = lgb.train(params, lgb.Dataset(X, y), num_boost_round=60)
    meta = {"purpose": "sap", "features": cols, "categories": cats, "reference_year": 2026,
            "features_version": F.FEATURES_VERSION}
    v = registry.save_booster("sap", b, meta, models_dir=models_dir)
    registry.register("sap", v, True, {"synthetic": True}, {})
    return v


def use_tmp_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(registry, "REGISTRY_FILE", tmp_path / "model_registry.json")
    registry.clear()
    return tmp_path / "models", tmp_path / "model_registry.json"
