"""M4 energy model: York -> NEED feature mapping, abstain paths, switch-gated baseline, quantile spread (synthetic)."""
import json
import math

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from backend.app import config
from backend.app.ml import features as F, registry
from backend.app.ml.tuning import BASE_PARAMS
from backend.app.schemas.enums import MeasureId as M, Provenance
from backend.app.services import energy_model as E
from backend.app.services.baseline import get_baseline
from tests.conftest import make_home
from tests.unit.ml_synthetic import use_tmp_registry

COLS = list(F.FEATURE_SETS["energy_york"])
BENCH = {"baseline_gas_kwh": Provenance.population_benchmark, "baseline_elec_kwh": Provenance.population_benchmark}


def gh(**kw):
    """A gas-heated home whose baselines are NEED benchmarks (make_home leaves provenance empty)."""
    kw.setdefault("main_fuel", "mains gas (not community)")
    kw.setdefault("provenance", dict(BENCH))
    return make_home(**kw)


def test_york_home_maps_to_need_codes():
    h = make_home(property_type="House", built_form="Enclosed Mid-Terrace", age_end=1966.0, floor_area_m2=120.0,
                  rating="E", main_fuel="mains gas (not community)", solar_pv=True)
    r = F.features(F.state_from_home(h), "energy_york")
    assert r == {"need_property_type": "Mid terrace", "need_age_band": 2.0, "need_floor_area_band": 3.0,
                 "need_epc_band": "E", "need_main_heat_gas": 1.0, "solar_pv": 1.0, "need_region": "E12000003"}
    f = F.features(F.state_from_home(make_home(property_type="Maisonette", rating="B", main_fuel="electricity")), "energy_york")
    assert f["need_property_type"] == "Flat" and f["need_epc_band"] == "A/B" and f["need_main_heat_gas"] == 0.0


def test_need_only_fields_are_not_features():
    assert not {"council_tax_band", "imd_quintile", "loft_insulation_scheme", "cavity_wall_insulation_scheme"} & set(COLS)


def _train(models_dir, fuel, scale, alphas=(None,)):
    rng = np.random.default_rng(1)
    rows = []
    for _ in range(400):
        rows.append({"need_property_type": str(rng.choice(["Detached", "Flat", "Mid terrace"])), "need_age_band": float(rng.integers(1, 5)),
                     "need_floor_area_band": float(rng.integers(1, 6)), "need_epc_band": str(rng.choice(["C", "D", "E"])),
                     "need_main_heat_gas": 1.0, "solar_pv": 0.0, "need_region": "E12000003"})
    df = pd.DataFrame(rows)
    y = np.log(scale) + 0.2 * df.need_floor_area_band.to_numpy() + rng.normal(0, 0.3, len(df))
    cats = F.fit_categories(df, COLS)
    X = F.to_frame(df, COLS, cats)
    for a in alphas:
        p = {**BASE_PARAMS, "num_threads": 1, "num_leaves": 7, "min_data_in_leaf": 10,
             **({"objective": "quantile", "alpha": a} if a else {"objective": "regression"})}
        name = f"energy_{fuel}" + (f"_q{int(a * 100)}" if a else "")
        v = registry.save_booster(name, lgb.train(p, lgb.Dataset(X, y), 40), {"features": COLS, "categories": cats}, models_dir)
        registry.register(name, v, True, {}, {})


@pytest.fixture
def tiny(monkeypatch, tmp_path):
    d, f = use_tmp_registry(monkeypatch, tmp_path)
    for fuel, scale in (("gas", 10000.0), ("elec", 3000.0)):
        _train(d, fuel, scale, alphas=(None, 0.1, 0.5, 0.9))
    yield
    registry.clear()


def test_abstains_without_models(monkeypatch, tmp_path):
    use_tmp_registry(monkeypatch, tmp_path)
    h = make_home(main_fuel="mains gas (not community)")
    assert E.point(h, "gas") is None and E.quantiles(h, "elec") is None and E.quantile_sigmas(h) == {}
    registry.clear()


def test_gas_only_for_gas_heated_homes(tiny):
    assert E.point(make_home(main_fuel="mains gas (not community)"), "gas") > 0
    assert E.point(make_home(main_fuel="electricity (not community)", heating_type="electric"), "gas") is None
    assert E.point(make_home(main_fuel="mains gas (not community)", mains_gas=False), "gas") is None


def test_quantiles_sorted_and_sigma_positive(tiny):
    h = make_home(main_fuel="mains gas (not community)")
    q = E.quantiles(h, "gas")
    assert q[0] <= q[1] <= q[2]
    s = E.quantile_sigmas(h)
    assert set(s) == {"gas_sigma_log", "elec_sigma_log"} and all(v > 0 for v in s.values())
    assert s["gas_sigma_log"] == pytest.approx(math.log(q[2] / q[0]) / (2 * E.Z90))


def test_baseline_uses_model_only_when_switch_on_and_requested(tiny, monkeypatch):
    h = gh()
    monkeypatch.setattr(config, "model_switch", lambda: {"use_model_baseline": False, "beat_benchmark": False})
    b = get_baseline(h, use_model=True)
    assert b.gas_provenance == Provenance.population_benchmark and "did not beat" in b.note
    monkeypatch.setattr(config, "model_switch", lambda: {"use_model_baseline": True, "beat_benchmark": True})
    assert get_baseline(h).gas_provenance == Provenance.population_benchmark      # not requested
    b = get_baseline(h, use_model=True)
    assert b.gas_provenance == Provenance.modelled and b.elec_provenance == Provenance.modelled and b.source == "modelled"
    assert b.gas_kwh == pytest.approx(E.point(h, "gas"))


def test_observed_zero_gas_is_never_replaced(tiny, monkeypatch):
    monkeypatch.setattr(config, "model_switch", lambda: {"use_model_baseline": True, "beat_benchmark": True})
    h = gh(mains_gas=False, heating_type="electric", main_fuel="electricity (not community)", baseline_gas_kwh=0.0,
           gas_status="no_mains_gas", prov_baseline_gas_kwh="observed",
           provenance={"baseline_gas_kwh": Provenance.observed, "baseline_elec_kwh": Provenance.population_benchmark})
    b = get_baseline(h, use_model=True)
    assert b.gas_kwh == 0.0 and b.gas_provenance == Provenance.observed and b.elec_provenance == Provenance.modelled
    assert b.source == "mixed"


def test_scenario_request_flag(tiny, monkeypatch):
    from backend.app.schemas.scenario import ScenarioRequest
    from backend.app.services.scenario_builder import build
    monkeypatch.setattr(config, "model_switch", lambda: {"use_model_baseline": True, "beat_benchmark": True})
    h = gh()
    r0 = build(ScenarioRequest(home_id=h.home_id, measures=[M.cavity_wall], include_packages=False), h)
    r1 = build(ScenarioRequest(home_id=h.home_id, measures=[M.cavity_wall], include_packages=False, use_model_baseline=True), h)
    assert r0.baseline.source == "population_benchmark" and r1.baseline.source == "modelled"
    assert r0.scenario_id != r1.scenario_id


def test_quantile_spread_replaces_calibrated_lognormal_only(tiny, monkeypatch):
    from backend.app.services.feasibility import assess
    from backend.app.services.uncertainty import run
    from backend.app.schemas.scenario import Assumptions
    h = make_home(main_fuel="mains gas (not community)")
    u = run(h, get_baseline(h), assess(h), [M.cavity_wall], Assumptions(), "0" * 64)
    assert not any("baseline" in x for x in u["inputs_varied"])      # uncalibrated: nothing to replace
    monkeypatch.setattr(config, "engine_calibration", lambda: {"version": "t", "baseline_spread": {"gas_sigma_log": 0.4, "elec_sigma_log": 0.3}})
    u = run(h, get_baseline(h), assess(h), [M.cavity_wall], Assumptions(), "0" * 64)
    assert any("quantile models" in x for x in u["inputs_varied"])


def test_model_switch_file_shape_when_present():
    p = config.CONFIGS / "model_switch.json"
    if not p.exists():
        pytest.skip("model_switch.json not written yet")
    sw = json.loads(p.read_text())
    assert {"use_model_baseline", "beat_benchmark", "model_version", "val_mae", "benchmark_val_mae"} <= set(sw)
    assert sw["use_model_baseline"] == (sw["per_fuel_gate"]["gas"] and sw["per_fuel_gate"]["elec"])
