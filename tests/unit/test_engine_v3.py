"""engine-v3 (docs/IMPROVEMENT_PLAN.md): correctness fixes A1-A9."""
import pytest

from backend.app import config
from backend.app.schemas.enums import FeasibilityState as F, MeasureId as M, Suitability as Su
from backend.app.schemas.scenario import Assumptions
from backend.app.services import costs, feasibility, impacts
from backend.app.services.baseline import get_baseline
from backend.app.services.simulator import simulate
from tests.conftest import make_home

ABS = 1e-6
HEADLINE = Assumptions(segment_impacts=False)


# ---- A1 (D19): PV saving does not grow with heat-pump electricity ----

def test_pv_saving_same_with_or_without_heat_pump():
    h = make_home()
    b = get_baseline(h)
    alone = simulate(b, h, [M.solar_pv], HEADLINE).elec_saving_kwh
    pkg = simulate(b, h, [M.heat_pump, M.solar_pv], HEADLINE)
    pv_step = next(s for s in pkg.steps if s.measure == M.solar_pv)
    assert alone == pytest.approx(0.12228 * 3000, abs=ABS)
    assert pv_step.elec_saving_kwh == pytest.approx(alone, abs=ABS)


def test_pv_never_offsets_more_than_import():
    h = make_home()
    b = get_baseline(h)
    s = simulate(b, h, [M.solar_pv], HEADLINE, impact_overrides={M.solar_pv: 5.0})
    assert s.after.elec_import == pytest.approx(0.0, abs=ABS)


# ---- A2 (D20): roof type decides whether loft insulation applies ----

@pytest.mark.parametrize("desc,state,code", [
    ("Flat, no insulation (assumed)", F.infeasible, "flat_roof"),
    ("Roof room(s), no insulation (assumed)", F.needs_verification, "room_in_roof"),
    ("Pitched, insulated at rafters", F.needs_verification, "insulated_at_rafters"),
    ("Thatched", F.needs_verification, "thatched_roof"),
    ("Average thermal transmittance 0.50 W/m²K", F.needs_verification, "roof_type_unknown"),
    ("Pitched, 270 mm loft insulation", F.infeasible, "loft_already_deep"),
    ("Pitched, 300+ mm loft insulation", F.infeasible, "loft_already_deep"),
])
def test_loft_by_roof_type(desc, state, code):
    f = feasibility.loft(make_home(roof_rating="Poor", roof_description=desc))
    assert f.state == state and f.reason_code == code


@pytest.mark.parametrize("desc,rating,suit", [
    ("Pitched, 50 mm loft insulation", "Average", Su.high),        # thin loft insulation -> High even if rated Average
    ("Pitched, 150 mm loft insulation", "Average", Su.medium),
    ("Pitched, no insulation (assumed)", "Very Poor", Su.high),
    ("Pitched, 200 mm loft insulation", "Poor", Su.high),           # rating Poor -> High
])
def test_loft_suitability_from_depth(desc, rating, suit):
    f = feasibility.loft(make_home(roof_rating=rating, roof_description=desc))
    assert f.state == F.feasible and f.suitability == suit


def test_loft_depth_parse():
    assert feasibility.loft_depth_mm(make_home(roof_description="Pitched, 12 mm loft insulation")) == 12
    assert feasibility.loft_depth_mm(make_home(roof_description="Pitched, no insulation (assumed)")) == 0
    assert feasibility.loft_depth_mm(make_home(roof_description="Pitched, insulated (assumed)")) is None


def test_planning_note_for_pre_1919():
    old = make_home(age_band="before 1900", walls_rating="Poor", walls_description="Solid brick, as built, no insulation (assumed)")
    new = make_home(age_band="1950-1966", walls_rating="Poor", walls_description="Solid brick, as built, no insulation (assumed)")
    assert "conservation-area" in feasibility.solid(old).reason_text
    assert "conservation-area" not in feasibility.solid(new).reason_text
    assert "conservation-area" in feasibility.solar(old).reason_text


# ---- A5 (D15 rev.): correlated segments are not added together ----

def test_max_rule_uses_region_plus_largest_single_adjustment():
    h = make_home(rating="E", age_band="before 1900", built_form="Mid-Terrace",
                  walls_description="Solid brick, as built, no insulation (assumed)")
    value, d = impacts.impact("solid_wall", "mid", h)
    shrunk = {k: v["shrunk"] for k, v in d["segments"].items() if isinstance(v, dict) and "shrunk" in v}
    others = [v for k, v in shrunk.items() if k != "region"]
    assert value == pytest.approx(0.172759 + shrunk["region"] + max(others, key=abs), abs=1e-6)
    assert 0.10 < value < 0.172759              # was 2.8% when all three were added
    assert sum(1 for k, v in d["segments"].items() if isinstance(v, dict) and v.get("used")) == 2


def test_backfit_effects_used_when_calibrated(monkeypatch):
    cal = {"version": "t", "segment_effects": {"cavity_wall": {"epc_rating": {"E-G": 0.01}, "property_type": {"Detached": 0.02}}}}
    monkeypatch.setattr(config, "engine_calibration", lambda: cal)
    h = make_home(rating="E", age_band="1967-1975", built_form="Detached")
    value, d = impacts.impact("cavity_wall", "mid", h)
    region = impacts.shrinkage("cavity_wall")["region"]["Yorkshire and the Humber"]["shrunk"]
    assert d["segments"]["rule"] == "backfit"
    assert value == pytest.approx(0.11982 + region + 0.01 + 0.02, abs=1e-9)


# ---- A6 (D23): partial glazing priced for the windows actually replaced ----

def test_partial_glazing_cost():
    full = config.measure_spec("double_glazing")["cost"]["mid"]
    assert costs.measure_cost(M.double_glazing, make_home(glazing="single"))[0] == pytest.approx(full)
    assert costs.measure_cost(M.double_glazing, make_home(glazing="partial", multi_glaze_pct=87.0))[0] == pytest.approx(0.13 * full)
    assert costs.measure_cost(M.double_glazing, make_home(glazing="partial", multi_glaze_pct=None))[0] == pytest.approx(0.5 * full)


def test_size_scaling_only_when_reference_area_known(monkeypatch):
    h = make_home(floor_area_m2=200.0)
    base = config.measure_spec("solid_wall")["cost"]["mid"]
    assert costs.measure_cost(M.solid_wall, h)[0] == pytest.approx(base)
    monkeypatch.setattr(config, "engine_calibration", lambda: {"version": "t", "reference_floor_area_m2": 100.0})
    assert costs.measure_cost(M.solid_wall, h)[0] == pytest.approx(base * 2 ** 0.75)
    assert costs.measure_cost(M.solar_pv, h)[0] == pytest.approx(config.measure_spec("solar_pv")["cost"]["mid"])   # exponent 0
    assert costs.measure_cost(M.loft_insulation, make_home(floor_area_m2=1000.0))[0] == pytest.approx(
        config.measure_spec("loft_insulation")["cost"]["mid"] * 2.0)   # clamped


# ---- A7 (D24): field-evidence SCOP ----

def test_scop_from_field_evidence():
    assert config.catalogue_globals()["heat_pump_scop"] == {"low": 2.44, "mid": 2.80, "high": 3.5}
    h = make_home()
    s = simulate(get_baseline(h), h, [M.heat_pump], HEADLINE)
    assert s.elec_saving_kwh == pytest.approx(-11634 * 0.85 / 2.8, abs=ABS)


# ---- A8 (D25): thermostat saving depends on the controls already installed ----

@pytest.mark.parametrize("controls,level,impact", [("none", "mid", 0.10), ("timer", "mid", 0.075), ("full", "mid", 0.05),
                                                    ("none", "low", 0.075), ("full", "high", 0.075), ("full", "low", 0.05)])
def test_thermostat_level_by_controls(controls, level, impact):
    assert impacts.impact("smart_thermostat", level, make_home(controls=controls))[0] == pytest.approx(impact)


def test_thermostat_saving_falls_with_better_controls():
    savings = []
    for c in ("none", "timer", "full"):
        h = make_home(controls=c)
        savings.append(simulate(get_baseline(h), h, [M.smart_thermostat], HEADLINE).gas_saving_kwh)
    assert savings[0] > savings[1] > savings[2]
