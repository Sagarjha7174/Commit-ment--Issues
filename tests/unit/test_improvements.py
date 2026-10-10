"""Engine refinements D15-D18: segment-aware impacts, electric heating, NEED-calibrated combinations, boiler efficiency."""
import json
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

from backend.app import config
from backend.app.schemas.enums import CombinationMode, MeasureId as M, ValueStatus
from backend.app.schemas.scenario import Assumptions, ScenarioRequest
from backend.app.services import impacts, units
from backend.app.services.baseline import get_baseline
from backend.app.services.carbon import carbon_change
from backend.app.services.scenario_builder import build
from backend.app.services.simulator import simulate
from tests.conftest import make_home

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines"))
ABS = 1e-6
HEADLINE = Assumptions(segment_impacts=False)


# ---------------- D15 segment-aware impacts ----------------

@pytest.mark.parametrize("band,seg", [("before 1900", "Pre 1919"), ("1900-1929", "Pre 1919"), ("1930-1949", "1919-44"),
                                      ("1950-1966", "1945-64"), ("1967-1975", "1965-82"), ("1976-1982", "1965-82"),
                                      ("1996-2002", "1983-99"), ("2003-2006", "2000 onwards"), ("2012 onwards", "2000 onwards"),
                                      ("2008", "2000 onwards"), (None, None)])
def test_age_segment(band, seg):
    assert impacts.age_segment(band) == seg


def test_type_segment_flats_have_none():
    assert impacts.type_segment("Flat", "Detached") is None
    assert impacts.type_segment("House", "Enclosed Mid-Terrace") == "Mid terrace"
    assert impacts.type_segment("Bungalow", "Semi-Detached") == "Bungalow"


def test_shrinkage_weights_bounded_and_noise_fully_shrunk():
    for m in ("loft_insulation", "cavity_wall", "solid_wall", "solar_pv"):
        for rows in impacts.shrinkage(m).values():
            for r in rows.values():
                assert 0.0 <= r["weight"] <= 1.0
                assert abs(r["shrunk"]) <= abs(r["deviation"]) + 1e-12
    # loft by EPC band: segment spread is within sampling noise -> no adjustment
    assert all(r["weight"] == 0.0 for r in impacts.shrinkage("loft_insulation")["epc_rating"].values())


def test_segment_impact_hand_calc_cavity():
    """Independent recomputation of the empirical-Bayes adjustment for one home from the catalogue numbers."""
    spec = config.measure_spec("cavity_wall")
    home = make_home(rating="E", age_band="1967-1975", built_form="Detached")
    wanted = {"epc_rating": "E-G", "property_age": "1965-82", "property_type": "Detached", "region": "Yorkshire and the Humber"}
    shrunk = {}
    for dim, seg_name in wanted.items():
        segs = spec["impact_by_segment"][dim]["segments"]
        head = segs["All domestic properties"]["median_pct"]
        rows = {k: v for k, v in segs.items() if k != "All domestic properties" and v["status"] == "observed"}
        se = {k: 1.2533 * ((v["q3"] - v["q1"]) / 1.349) / math.sqrt(v["n"]) for k, v in rows.items()}
        dev = {k: v["median_pct"] - head for k, v in rows.items()}
        mean = sum(dev.values()) / len(dev)
        tau2 = max(0.0, sum((d - mean) ** 2 for d in dev.values()) / (len(dev) - 1) - sum(s ** 2 for s in se.values()) / len(se))
        w = tau2 / (tau2 + se[seg_name] ** 2) if tau2 > 0 else 0.0
        shrunk[dim] = w * dev[seg_name]
    # D15 rev. "max" rule: region + the single largest non-region adjustment (no backfit calibration in the repo)
    others = [v for k, v in shrunk.items() if k != "region"]
    total = shrunk["region"] + max(others, key=abs)
    value, detail = impacts.impact("cavity_wall", "mid", home)
    assert detail["segments"]["rule"] == "max" and detail["segments"]["property_type"]["used"]
    assert value == pytest.approx(spec["impact"]["mid"] + total, abs=1e-12)
    assert detail["headline"] == spec["impact"]["mid"]
    s = simulate(get_baseline(home), home, [M.cavity_wall])
    assert s.gas_saving_kwh == pytest.approx(value * 12000, abs=ABS)


def test_segment_disabled_gives_headline():
    home = make_home(rating="E", age_band="1967-1975", built_form="Detached")
    assert impacts.impact("cavity_wall", "mid", home, enabled=False)[0] == config.measure_spec("cavity_wall")["impact"]["mid"]
    s = simulate(get_baseline(home), home, [M.cavity_wall], HEADLINE)
    assert s.gas_saving_kwh == pytest.approx(0.11982 * 12000, abs=ABS)


def test_segment_impact_floored_at_zero(monkeypatch):
    monkeypatch.setattr(impacts, "adjustment", lambda m, h: (-1.0, {}))
    assert impacts.impact("loft_insulation", "mid", make_home())[0] == 0.0


def test_glazing_and_thermostat_not_segmented():
    h = make_home(glazing="single", controls="timer", rating="E", built_form="Detached")
    assert impacts.impact("double_glazing", "mid", h)[1] is None
    assert impacts.impact("smart_thermostat", "mid", h)[1] is None


# ---------------- D16 electrically heated homes ----------------

SPLIT = {"version": "elec-split-test", "shares": {"Flat|A/B": {"share": 0.5}, "*|D": {"share": 0.4}, "*|*": {"share": 0.3}}}


def electric_home(**kw):
    base = dict(property_type="Flat", built_form="Detached", rating="B", heating_type="electric", heating_rating="Average",
                mains_gas=False, baseline_gas_kwh=0.0, gas_status="no_mains_gas", prov_baseline_gas_kwh="observed",
                baseline_elec_kwh=2700.0, controls="timer", glazing="double", roof_rating=None,
                roof_rating_status="not_applicable", roof_description="(another dwelling above)",
                walls_rating="Poor", walls_description="Cavity wall, as built, no insulation (assumed)", age_end=1990.0)
    base.update(kw)
    return make_home(**base)


def test_without_split_electric_home_abstains(monkeypatch):
    monkeypatch.setattr(config, "electric_heating_split", lambda: None)
    h = electric_home()
    b = get_baseline(h)
    assert not b.elec_heated and "not built" in b.note
    s = simulate(b, h, [M.smart_thermostat, M.heat_pump])
    assert {r.measure: r.reason_code for r in s.measures} == {M.smart_thermostat: "heating_not_on_gas",
                                                               M.heat_pump: "no_gas_to_displace"}


def test_split_lookup_falls_back(monkeypatch):
    monkeypatch.setattr(config, "electric_heating_split", lambda: SPLIT)
    assert units.electric_heating_share(electric_home())[0] == 0.5                       # Flat|A/B
    assert units.electric_heating_share(electric_home(property_type="House", rating="D"))[0] == 0.4   # *|D
    assert units.electric_heating_share(electric_home(rating="F"))[0] == 0.3             # *|*
    assert units.electric_heating_share(make_home())[0] is None                           # gas boiler


def test_electric_home_thermostat_and_heat_pump(monkeypatch):
    monkeypatch.setattr(config, "electric_heating_split", lambda: SPLIT)
    h = electric_home()
    b = get_baseline(h)
    assert b.elec_heated and b.elec_heat_share == 0.5 and not b.gas_heated
    heat = 0.5 * 2700.0
    space, water = 0.77 * heat, 0.23 * heat
    s = simulate(b, h, [M.smart_thermostat], HEADLINE)
    assert s.before.elec_space == pytest.approx(space) and s.before.elec_water == pytest.approx(water)
    assert s.before.elec_base == pytest.approx(2700.0 - heat)
    assert s.gas_saving_kwh == pytest.approx(0.0, abs=ABS)
    assert s.elec_saving_kwh == pytest.approx(0.075 * space, abs=ABS)        # thermostat mid 7.5% of space heat
    # heat pump replaces the remaining electric space + water heat: saving = heat x (1 - 1/SCOP)
    s2 = simulate(b, h, [M.smart_thermostat, M.heat_pump], HEADLINE)
    remaining = space * (1 - 0.075) + water
    assert s2.elec_saving_kwh == pytest.approx(0.075 * space + remaining * (1 - 1 / 2.8), abs=ABS)   # SCOP 2.80 (D24)
    assert s2.improvement_potential_status == ValueStatus.ok and s2.improvement_potential_pct > 0
    c = carbon_change(s2)
    assert c.gas_kg == pytest.approx(0.0, abs=ABS) and c.elec_kg > 0


def test_electric_home_fabric_uses_space_share_conversion(monkeypatch):
    monkeypatch.setattr(config, "electric_heating_split", lambda: SPLIT)
    h = electric_home(property_type="House", built_form="Semi-Detached", rating="D",
                      roof_rating="Poor", roof_rating_status="observed", roof_description="Pitched, 50 mm loft insulation")
    b = get_baseline(h)
    s = simulate(b, h, [M.loft_insulation], HEADLINE)
    space = 0.77 * 0.4 * 2700.0
    frac = 0.032117 / (0.77 * (1 - 0.0305))
    assert s.elec_saving_kwh == pytest.approx(frac * space, abs=ABS)


def test_electric_split_pipeline_build():
    import build_electric_heating_split as P
    rows = []
    for fuel_code, med in ((1, 2000.0), (2, 4000.0)):
        rows.append({"fuel": "elec", "level": "L2_fuel_type_epc", "need_main_fuel": fuel_code,
                     "need_property_type": "Flat", "need_epc_band": "C", "median": med, "n": 50})
        rows.append({"fuel": "elec", "level": "L3_fuel_epc", "need_main_fuel": fuel_code,
                     "need_property_type": None, "need_epc_band": "C", "median": med * 1.1, "n": 100})
    rows.append({"fuel": "elec", "level": "L2_fuel_type_epc", "need_main_fuel": 2, "need_property_type": "Detached",
                 "need_epc_band": "E", "median": 9000.0, "n": 5})   # below MIN_N: ignored
    out = P.build(pd.DataFrame(rows))
    assert out["shares"]["Flat|C"]["share"] == pytest.approx(0.5)
    assert out["shares"]["*|C"]["share"] == pytest.approx(0.5)
    assert out["shares"]["*|*"]["share"] == pytest.approx(0.5)
    assert "Detached|E" not in out["shares"]


# ---------------- D17 NEED-calibrated combinations ----------------

def test_calibration_file_reproduces_need_medians():
    cal = config.combination_calibration()
    assert cal is not None
    for r in cal["combinations"]:
        assert r["calibrated_pct"] == pytest.approx(r["need_median_pct"], abs=0.01)
        assert 0 < r["factor"] < 1
    assert 0 < cal["pooled_factor"] < 1


def test_calibrated_mode_lowers_combined_fabric_and_reconciles():
    h = make_home(roof_rating="Poor")
    b = get_baseline(h)
    eng = simulate(b, h, [M.loft_insulation, M.cavity_wall], HEADLINE)
    cal = simulate(b, h, [M.loft_insulation, M.cavity_wall], HEADLINE.model_copy(update={"combination_mode": CombinationMode.need_calibrated}))
    assert cal.gas_saving_kwh < eng.gas_saving_kwh
    assert 100 * cal.gas_saving_kwh / 12000 == pytest.approx(8.38, abs=0.01)   # NEED median, same basis
    assert any(w.startswith("NEED-calibrated") for w in cal.warnings)


def test_calibrated_mode_does_not_touch_single_measures():
    h = make_home()
    b = get_baseline(h)
    a = HEADLINE.model_copy(update={"combination_mode": CombinationMode.need_calibrated})
    assert simulate(b, h, [M.cavity_wall, M.heat_pump], a).gas_saving_kwh == \
        pytest.approx(simulate(b, h, [M.cavity_wall, M.heat_pump], HEADLINE).gas_saving_kwh, abs=ABS)


def test_scenario_reports_calibrated_reference_next_to_engineering():
    h = make_home(roof_rating="Poor", glazing="single", controls="timer")
    r = build(ScenarioRequest(home_id=h.home_id, measures=["loft_insulation", "cavity_wall", "smart_thermostat"]), h)
    cc = r.combination_check
    assert cc is not None and cc["gas_saving_kwh"] < r.simulation.gas_saving_kwh
    assert cc["label"].startswith("NEED-calibrated reference")
    one = build(ScenarioRequest(home_id=h.home_id, measures=["cavity_wall"]), h)
    assert one.combination_check is None
    multi = [p for p in r.packages.packages if p.calibrated is not None]
    assert multi and all(p.calibrated["carbon_saving_kg"] <= p.carbon_saving_kg + 1e-9 for p in multi)


# ---------------- D18 boiler efficiency by heating rating ----------------

@pytest.mark.parametrize("rating,eff", [("Very Good", 0.89), ("Good", 0.85), ("Average", 0.75), ("Poor", 0.67),
                                        ("Very Poor", 0.6), (None, 0.85)])
def test_boiler_efficiency_by_rating(rating, eff):
    assert units.resolve(Assumptions(), make_home(heating_rating=rating)).boiler_efficiency == eff


def test_boiler_efficiency_override_wins():
    assert units.resolve(Assumptions(boiler_efficiency=0.9), make_home(heating_rating="Poor")).boiler_efficiency == 0.9


def test_heat_pump_electricity_scales_with_boiler_efficiency_fabric_does_not():
    good, poor = make_home(heating_rating="Good"), make_home(heating_rating="Poor")
    hp_good = simulate(get_baseline(good), good, [M.heat_pump], HEADLINE)
    hp_poor = simulate(get_baseline(poor), poor, [M.heat_pump], HEADLINE)
    heat_water = 12000 * (1 - 0.0305)
    assert hp_good.elec_saving_kwh == pytest.approx(-heat_water * 0.85 / 2.8, abs=ABS)
    assert hp_poor.elec_saving_kwh == pytest.approx(-heat_water * 0.67 / 2.8, abs=ABS)
    cav = [simulate(get_baseline(h), h, [M.cavity_wall], HEADLINE).gas_saving_kwh for h in (good, poor)]
    assert cav[0] == pytest.approx(cav[1], abs=ABS)


def test_versions_include_engine_params():
    v = config.versions()
    assert v["engine_params"] == json.loads((ROOT / "configs/engine_params.json").read_text())["version"]
    assert v["combination_calibration"] == config.combination_calibration()["version"]
