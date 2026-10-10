"""M5 recommender: only feasible measures, calibrated probability order, fallbacks, install sequence (synthetic)."""
import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from backend.app.ml import features as F, registry
from backend.app.ml.tuning import BASE_PARAMS
from backend.app.schemas.enums import MEASURE_ORDER, FeasibilityState, MeasureId as M
from backend.app.schemas.scenario import ScenarioRequest
from backend.app.services import recommender as R
from backend.app.services.feasibility import assess
from backend.app.services.scenario_builder import build
from tests.conftest import make_home
from tests.unit.ml_synthetic import synthetic_homes, use_tmp_registry

COLS = list(F.FEATURE_SETS["recommender"])


def _train_rec(models_dir, measure: str, target):
    homes = synthetic_homes(300, seed=5)
    df = pd.DataFrame([F.features(F.state_from_home(h), "recommender") for h in homes])
    y = np.array([target(h) for h in homes], dtype=float)
    cats = F.fit_categories(df, COLS)
    b = lgb.train({**BASE_PARAMS, "objective": "binary", "num_threads": 1, "num_leaves": 7, "min_data_in_leaf": 5},
                  lgb.Dataset(F.to_frame(df, COLS, cats), y), 30)
    meta = {"features": COLS, "categories": cats, "isotonic": {"x": [0.0, 1.0], "y": [0.0, 1.0]}}
    v = registry.save_booster(f"rec_{measure}", b, meta, models_dir)
    registry.register(f"rec_{measure}", v, True, {}, {})


def _tables(models_dir, shipped=True):
    tab = {m.value: {"cell": {}, "type": {}, "all": 0.05 * (i + 1)} for i, m in enumerate(MEASURE_ORDER)}
    v = registry.save_json_model("recommender_ranking", {"b1_prevalence": tab}, models_dir)
    registry.register("recommender_ranking", v if shipped else None, shipped, {}, {})


@pytest.fixture
def tiny(monkeypatch, tmp_path):
    d, _ = use_tmp_registry(monkeypatch, tmp_path)
    _train_rec(d, "double_glazing", lambda h: h.glazing != "double")
    _tables(d)
    yield
    registry.clear()


def _home():
    return make_home(glazing="single", walls_rating="Poor", roof_rating="Poor", controls="timer", solar_pv=False)


def test_only_non_infeasible_measures_and_verify_flag(tiny):
    h = _home().model_copy(update={"controls": None})
    feas = assess(h)
    r = R.ranking(h, feas, {})
    infeasible = {f.measure.value for f in feas if f.state == FeasibilityState.infeasible}
    assert not infeasible & {x["measure"] for x in r}
    therm = next(x for x in r if x["measure"] == "smart_thermostat")
    assert therm["verify"] and therm["must_verify"] == ["controls"]


def test_sorted_by_probability_then_ranks_contiguous(tiny):
    r = R.ranking(_home(), assess(_home()), {})
    probs = [x["assessor_relevance_prob"] for x in r]
    assert probs == sorted(probs, reverse=True) and [x["rank"] for x in r] == list(range(1, len(r) + 1))
    dg = next(x for x in r if x["measure"] == "double_glazing")
    assert "classifier" in dg["basis"]
    assert all("prevalence" in x["basis"] for x in r if x["measure"] != "double_glazing")


def test_ties_broken_by_carbon_per_pound(tiny, monkeypatch):
    monkeypatch.setattr(R, "probability", lambda h, m: (0.5, "tie"))
    sa = {"loft_insulation": {"carbon_saving_kg": 100.0, "net_cost_gbp": 1000.0},
          "cavity_wall": {"carbon_saving_kg": 400.0, "net_cost_gbp": 1000.0}}
    r = R.ranking(_home(), assess(_home()), sa)
    assert [x["measure"] for x in r][:2] == ["cavity_wall", "loft_insulation"]
    assert r[0]["carbon_per_pound_kg"] == pytest.approx(0.4)


def test_engine_order_when_ranking_model_not_shipped(monkeypatch, tmp_path):
    d, _ = use_tmp_registry(monkeypatch, tmp_path)
    _tables(d, shipped=False)
    r = R.ranking(_home(), assess(_home()), {})
    assert all(x["assessor_relevance_prob"] is None for x in r)
    suits = [R.SUIT_RANK.get(x["suitability"], 0) for x in r]
    assert suits == sorted(suits, reverse=True)
    registry.clear()


def test_install_sequence_is_engine_physical_order(tiny):
    r = R.ranking(_home(), assess(_home()), {})
    seq = R.install_sequence(r)
    assert seq == [m.value for m in MEASURE_ORDER if m.value in {x["measure"] for x in r}]
    assert R.install_sequence(None) is None


def test_scenario_result_carries_ranking(tiny):
    h = _home()
    res = build(ScenarioRequest(home_id=h.home_id, include_packages=False), h)
    assert res.recommendation_ranking and res.install_sequence
    assert res.install_sequence[-1] in ("solar_pv", "heat_pump", "smart_thermostat", "double_glazing")
