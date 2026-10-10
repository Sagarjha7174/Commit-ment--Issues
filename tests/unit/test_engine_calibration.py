"""engine-v3 phase A2: data calibration (pipelines/build_engine_calibration.py) and the engine hooks that use it."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.app import config
from backend.app.services import baseline as base_mod
from backend.app.services.baseline import area_band, area_factor, get_baseline
from backend.app.services.score import score_home
from tests.conftest import make_home

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipelines"))
import build_engine_calibration as P  # noqa: E402

CAL = {"version": "test-cal",
       "area_elasticity": {"gas": 0.5, "elec": 0.3, "band_reference_area_m2": {"1": 40.0, "2": 75.0, "3": 125.0, "4": 175.0, "5": 250.0}},
       "missing_part_priors": {"renewables": {"stale_epc": 1.5, "recent_epc": 4.0}, "windows": 70.0}}


# ---------------- pipeline functions ----------------

def test_fit_area_elasticity_recovers_beta():
    rng = np.random.default_rng(0)
    rows = []
    for ptype, level in (("Detached", 1.3), ("Mid terrace", 0.9)):
        for band, rep in ((2, 75.0), (3, 125.0), (4, 175.0)):
            for _ in range(200):
                noise = rng.normal(0, 0.05)
                rows.append({"floor_area_band_code": band, "floor_area_m2_rep": rep, "main_heat_gas": 1, "property_type": ptype,
                             "epc_band": "D", "gas_status": "metered", "elec_status": "metered",
                             "gas_kwh": 1000 * level * rep ** 0.6 * np.exp(noise), "elec_kwh": 300 * level * rep ** 0.35 * np.exp(noise)})
    out = P.fit_area_elasticity(pd.DataFrame(rows))
    assert out["gas"] == pytest.approx(0.6, abs=0.02) and out["elec"] == pytest.approx(0.35, abs=0.02)
    assert out["band_reference_area_m2"] == {"2": 75.0, "3": 125.0, "4": 175.0}


def _total(seg, eff):
    return sum(seg[d].map(lambda v, d=d: eff[d].get(v, 0.0) if v else 0.0) for d in eff if d != "residual_max_abs")


def test_backfit_reproduces_contrasts_with_correlated_segments():
    # old homes are mostly mid-terrace and poorly rated: marginal deviations overlap
    seg = pd.DataFrame([{"epc_rating": "E-G", "property_age": "Pre 1919", "property_type": "Mid terrace"}] * 60 +
                       [{"epc_rating": "E-G", "property_age": "1945-64", "property_type": "Semi detached"}] * 20 +
                       [{"epc_rating": "A-C", "property_age": "1945-64", "property_type": "Semi detached"}] * 50 +
                       [{"epc_rating": "A-C", "property_age": "Pre 1919", "property_type": "Mid terrace"}] * 10)
    targets = {"epc_rating": {"E-G": -0.05, "A-C": 0.03}, "property_age": {"Pre 1919": -0.05, "1945-64": 0.04},
               "property_type": {"Mid terrace": -0.05, "Semi detached": 0.03}}
    eff = P.backfit(seg, targets)
    total = _total(seg, eff)
    for d, t in targets.items():   # contrasts between segments are reproduced
        (s1, v1), (s2, v2) = t.items()
        assert total[seg[d] == s1].mean() - total[seg[d] == s2].mean() == pytest.approx(v1 - v2, abs=eff["residual_max_abs"] * 2 + 1e-6)
    # age and type are perfectly collinear here, so they share one effect instead of adding up:
    # the old, mid-terrace, E-G home gets about -5 pp, not the naive -15 pp sum of the three marginals
    assert total[0] == pytest.approx(-0.049, abs=0.002)


def test_backfit_independent_segments_reduce_to_targets():
    seg = pd.DataFrame([{"a": x, "b": y} for x in ("p", "q") for y in ("r", "s") for _ in range(25)])
    targets = {"a": {"p": 0.02, "q": -0.02}, "b": {"r": 0.01, "s": -0.01}}
    eff = P.backfit(seg, targets)
    assert eff["residual_max_abs"] < 1e-12
    assert eff["a"]["p"] - eff["a"]["q"] == pytest.approx(0.04, abs=1e-9)
    assert eff["b"]["r"] - eff["b"]["s"] == pytest.approx(0.02, abs=1e-9)


def test_backfit_partial_coverage_reports_residual():
    seg = pd.DataFrame([{"a": "p", "b": "r"}] * 40 + [{"a": "q", "b": None}] * 40 + [{"a": "q", "b": "s"}] * 20)
    eff = P.backfit(seg, {"a": {"p": 0.05, "q": -0.05}, "b": {"r": 0.04, "s": -0.04}})
    assert "residual_max_abs" in eff and np.isfinite(eff["residual_max_abs"])


def test_baseline_spread():
    bench = pd.DataFrame([{"level": "L1_fuel_type_epc_area", "fuel": f, "n": 100, "q1": 1000.0, "q3": 1000.0 * np.exp(1.349 * s)}
                          for f, s in (("gas", 0.4), ("gas", 0.4), ("elec", 0.3))])
    out = P.baseline_spread(bench)
    assert out["gas_sigma_log"] == pytest.approx(0.4) and out["elec_sigma_log"] == pytest.approx(0.3)


def test_missing_priors():
    scored = pd.DataFrame([{"flag_stale_epc": st, **{f"sub_{p}": v for p, v in subs.items()}} for st, subs in (
        (True, {"energy_efficiency": 50, "energy_intensity": 40, "insulation": 30, "heating": 80, "windows": 75, "renewables": 0, "smart_controls": 70}),
        (True, {"energy_efficiency": 60, "energy_intensity": None, "insulation": 50, "heating": 80, "windows": 10, "renewables": 0, "smart_controls": 40}),
        (False, {"energy_efficiency": 70, "energy_intensity": 60, "insulation": 80, "heating": 80, "windows": 75, "renewables": 60, "smart_controls": 100}))])
    pr = P.missing_priors(scored)
    assert pr["energy_intensity"] == pytest.approx(50.0) and pr["windows"] == pytest.approx(160 / 3, abs=1e-3)
    assert pr["renewables"] == {"stale_epc": 0.0, "recent_epc": 60.0}


# ---------------- engine hooks ----------------

@pytest.mark.parametrize("area,band", [(30, 1), (50, 1), (50.5, 2), (100, 2), (149, 3), (200, 4), (201, 5), (None, None)])
def test_area_band(area, band):
    assert area_band(area) == band


def test_area_factor_only_for_l1_cells_and_when_calibrated(monkeypatch):
    assert area_factor("gas", 199.0, "L1_fuel_type_epc_area")[0] == 1.0          # no calibration file
    monkeypatch.setattr(config, "engine_calibration", lambda: CAL)
    assert area_factor("gas", 199.0, "L1_fuel_type_epc_area")[0] == pytest.approx((199 / 175) ** 0.5)
    assert area_factor("elec", 151.0, "L1_fuel_type_epc_area")[0] == pytest.approx((151 / 175) ** 0.3)
    assert area_factor("gas", 199.0, "L2_fuel_type_epc")[0] == 1.0


def test_sawtooth_removed_in_baseline_and_score(monkeypatch):
    monkeypatch.setattr(config, "engine_calibration", lambda: CAL)
    homes = [make_home(floor_area_m2=a, benchmark_cell_level="L1_fuel_type_epc_area") for a in (151.0, 199.0)]
    b = [get_baseline(h) for h in homes]
    assert b[0].gas_kwh == pytest.approx(12000 * (151 / 175) ** 0.5) and b[1].gas_kwh == pytest.approx(12000 * (199 / 175) ** 0.5)
    assert "D21" in b[0].note
    # intensity gap between the two homes shrinks once the benchmark follows floor area
    raw_gap = (15000 / 151) - (15000 / 199)
    scaled = [(x.gas_kwh + x.elec_kwh) / h.floor_area_m2 for x, h in zip(b, homes)]
    assert 0 < scaled[0] - scaled[1] < raw_gap
    s = score_home(homes[0])
    intensity = next(p for p in s.parts if p.part == "energy_intensity")
    assert intensity.detail == f"{scaled[0]:.1f} kWh/m2/yr"


def test_user_reading_never_scaled(monkeypatch):
    from backend.app.schemas.scenario import UserReading
    monkeypatch.setattr(config, "engine_calibration", lambda: CAL)
    h = make_home(floor_area_m2=199.0, benchmark_cell_level="L1_fuel_type_epc_area")
    b = get_baseline(h, UserReading(gas_kwh=9000.0, elec_kwh=2500.0))
    assert b.gas_kwh == 9000.0 and b.elec_kwh == 2500.0


def test_missing_part_uses_prior(monkeypatch):
    monkeypatch.setattr(config, "engine_calibration", lambda: CAL)
    stale = score_home(make_home(solar_pv=None, flag_stale_epc=True))
    recent = score_home(make_home(solar_pv=None, flag_stale_epc=False))
    ren = lambda s: next(p for p in s.parts if p.part == "renewables")  # noqa: E731
    assert ren(stale).used_sub == 1.5 and ren(recent).used_sub == 4.0 and ren(stale).sub is None
    assert stale.range_low <= stale.total <= stale.range_high
    assert any("D22" in n for n in stale.notes)
    # without a prior for a part the old rule (50) still applies
    no_prior = score_home(make_home(controls=None))
    assert next(p for p in no_prior.parts if p.part == "smart_controls").used_sub == 50


def test_missing_prior_removes_the_plus_5_bias(monkeypatch):
    monkeypatch.setattr(config, "engine_calibration", lambda: CAL)
    none_pv = score_home(make_home(solar_pv=False, flag_stale_epc=True)).raw_total
    unknown = score_home(make_home(solar_pv=None, flag_stale_epc=True)).raw_total
    assert unknown - none_pv == pytest.approx(0.1 * 1.5)    # was +5.0 with the flat 50


# ---------------- end-to-end run on synthetic files (the real data is not in the repo) ----------------

def test_pipeline_main_end_to_end(tmp_path, monkeypatch):
    import json
    import freeze_score_params as FZ
    from backend.app.data import loaders
    from backend.app.schemas.property import SOURCE_COLUMNS

    rng = np.random.default_rng(1)
    rows = []
    for i in range(300):
        area = float(rng.choice([45, 80, 120, 160, 230]) + rng.integers(-4, 4))
        h = make_home(home_id=f"H{i}", split=("train", "val", "test")[i % 3], floor_area_m2=area,
                      rating=str(rng.choice(list("CDE"))), age_band=str(rng.choice(["before 1900", "1950-1966", "1983-1990"])),
                      built_form=str(rng.choice(["Mid-Terrace", "Semi-Detached", "Detached"])),
                      walls_description=str(rng.choice(["Solid brick, as built, no insulation (assumed)",
                                                        "Cavity wall, as built, no insulation (assumed)"])),
                      solar_pv=None if i % 7 == 0 else False, flag_stale_epc=bool(i % 2),
                      benchmark_cell_level="L1_fuel_type_epc_area")
        d = h.model_dump()
        r = {col: d.get(field) for col, field in SOURCE_COLUMNS.items()}
        r.update(postcode="YO1 1AA", epc_predicted_consumption_status="observed", flag_missing_heating=False)
        rows.append(r)
    homes = pd.DataFrame(rows)
    region = tmp_path / "region=york"
    region.mkdir()
    homes.to_parquet(region / "homes_tagged.parquet")
    need = pd.DataFrame([{"floor_area_band_code": b, "floor_area_m2_rep": rep, "main_heat_gas": 1, "property_type": "Detached",
                          "epc_band": "D", "gas_status": "metered", "elec_status": "metered",
                          "gas_kwh": 900 * rep ** 0.5 * np.exp(rng.normal(0, 0.1)), "elec_kwh": 400 * rep ** 0.3 * np.exp(rng.normal(0, 0.1))}
                         for b, rep in ((1, 40.0), (2, 75.0), (3, 125.0), (4, 175.0), (5, 250.0)) for _ in range(50)])
    need.to_parquet(tmp_path / "need_50k.parquet")
    pd.DataFrame([{"level": "L1_fuel_type_epc_area", "fuel": f, "n": 80, "q1": 1000.0, "q3": 1700.0} for f in ("gas", "elec")]
                 ).to_parquet(region / "benchmarks.parquet")

    cfg = tmp_path / "configs"
    cfg.mkdir()
    for f in config.CONFIGS.glob("*.json"):
        (cfg / f.name).write_text(f.read_text())
    (cfg / "emissions_factors.csv").write_text((config.CONFIGS / "emissions_factors.csv").read_text())
    monkeypatch.setattr(config, "CONFIGS", cfg)
    monkeypatch.setattr(config, "REGION_DIR", region)
    monkeypatch.setattr(loaders, "HOMES_TAGGED", region / "homes_tagged.parquet")
    monkeypatch.setattr(P, "OUT", cfg / "engine_calibration.json")
    monkeypatch.setattr(FZ, "SRC", region / "homes_tagged.parquet")
    monkeypatch.setattr(FZ, "OUT", cfg / "score_params.json")
    monkeypatch.setattr(FZ, "ROOT", tmp_path)
    for fn in (config._json, config.engine_calibration, loaders.homes_frame):
        fn.cache_clear()
    try:
        P.main(need_path=tmp_path / "need_50k.parquet")
        cal = json.loads((cfg / "engine_calibration.json").read_text())
        params = json.loads((cfg / "score_params.json").read_text())
    finally:
        for fn in (config._json, config.engine_calibration, loaders.homes_frame):
            fn.cache_clear()
    assert cal["area_elasticity"]["gas"] == pytest.approx(0.5, abs=0.05)
    assert cal["area_elasticity"]["band_reference_area_m2"]["3"] == 125.0
    assert 40 < cal["reference_floor_area_m2"] < 240
    assert set(cal["segment_effects"]) <= {"loft_insulation", "cavity_wall", "solid_wall", "solar_pv"} and cal["segment_effects"]
    assert cal["baseline_spread"]["gas_sigma_log"] == pytest.approx(np.log(1.7) / 1.349, abs=1e-3)
    assert set(cal["missing_part_priors"]["renewables"]) == {"stale_epc", "recent_epc"}
    assert params["version"] == "score-params-v2" and params["area_scaled_baselines"] is True
