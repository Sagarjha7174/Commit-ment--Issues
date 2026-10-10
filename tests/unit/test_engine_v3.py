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


# ---- B (D26, D27): bills, grants, payback, illustrative loan ----

from backend.app.schemas.scenario import ScenarioRequest  # noqa: E402
from backend.app.services import money  # noqa: E402
from backend.app.services.scenario_builder import build  # noqa: E402


def test_bill_arithmetic_at_price_cap():
    h = make_home()
    s = simulate(get_baseline(h), h, [M.cavity_wall], HEADLINE)
    b = money.bill_change(s)
    gas_saved = 0.11982 * 12000
    assert b["gas_saving_gbp"] == pytest.approx(gas_saved * 0.0797, abs=0.01)
    assert b["elec_saving_gbp"] == pytest.approx(0.0, abs=0.01) and b["standing_saving_gbp"] == pytest.approx(0.0, abs=0.01)
    before = 12000 * 0.0797 + 3000 * 0.2632 + 365 * (0.5483 + 0.2968)
    assert b["before_gbp"] == pytest.approx(before, abs=0.01)


def test_gas_standing_charge_saved_only_when_no_gas_left():
    h = make_home()
    b = get_baseline(h)
    keep = money.bill_change(simulate(b, h, [M.heat_pump], HEADLINE))                 # cooking gas stays
    gone = money.bill_change(simulate(b, h, [M.heat_pump], HEADLINE.model_copy(update={"other_gas_share": 0.0})))
    assert keep["standing_saving_gbp"] == pytest.approx(0.0, abs=0.01)
    assert gone["standing_saving_gbp"] == pytest.approx(365 * 0.2968, abs=0.01)


def test_price_override_for_heat_pump_tariff():
    h = make_home()
    s = simulate(get_baseline(h), h, [M.heat_pump], HEADLINE)
    cap = money.bill_change(s)
    cheap = money.bill_change(s, HEADLINE.model_copy(update={"elec_price_p": 15.0}))
    assert cheap["saving_gbp"] > cap["saving_gbp"] and "override" in cheap["prices"]["source"]


@pytest.mark.parametrize("heating,mains_gas,expected", [("gas_boiler", True, 7500.0), ("oil", False, 9000.0),
                                                        ("electric", False, 9000.0), ("heat_pump", False, 0.0)])
def test_boiler_upgrade_scheme(heating, mains_gas, expected):
    h = make_home(heating_type=heating, mains_gas=mains_gas)
    total, notes = money.grants_for([M.heat_pump], h, {"heat_pump": 17500.0})
    assert total == expected and notes
    assert money.grants_for([M.cavity_wall], h, {"cavity_wall": 1000.0})[0] == 0.0


def test_grant_never_exceeds_cost():
    assert money.grants_for([M.heat_pump], make_home(), {"heat_pump": 5000.0})[0] == 5000.0


def test_payback_and_loan():
    h = make_home()
    s = simulate(get_baseline(h), h, [M.cavity_wall], HEADLINE)
    f = money.finance_summary([M.cavity_wall], h, money.bill_change(s))
    assert f["net_cost_gbp"] == 1000.0 and f["payback_years"] == pytest.approx(1000 / f["annual_bill_saving_gbp"], abs=0.05)
    r, n = 0.07 / 12, 120
    assert f["illustrative_loan"]["monthly_repayment_gbp"] == pytest.approx(1000 * r / (1 - (1 + r) ** -n), abs=0.01)
    rising = money.finance_summary([M.heat_pump], h, {"status": "ok", "saving_gbp": -50.0})
    assert rising["payback_years"] is None and "not paid back" in rising["payback_note"]


def test_package_selection_uses_net_cost_and_no_grant_run_exists():
    h = make_home(roof_rating="Poor", glazing="single", controls="timer")
    r = build(ScenarioRequest(home_id=h.home_id, include_sensitivity=True), h)
    assert r.packages.cost_basis.startswith("net of grants")
    hp = next(p for p in r.packages.packages if p.package_id == "heat_pump")
    assert hp.grants_gbp == 7500.0 and hp.net_cost_gbp == hp.cost_gbp - 7500.0
    assert hp.carbon_per_pound_kg == pytest.approx(hp.carbon_saving_kg / hp.net_cost_gbp)
    assert "no_grants" in {x["name"] for x in r.sensitivity["runs"]}
    gross = build(ScenarioRequest(home_id=h.home_id, assumptions=Assumptions(apply_grants=False)), h)
    hp_g = next(p for p in gross.packages.packages if p.package_id == "heat_pump")
    assert gross.packages.cost_basis == "gross" and hp_g.carbon_per_pound_kg == pytest.approx(hp_g.carbon_saving_kg / hp_g.cost_gbp)


def test_scenario_reports_bills_and_finance():
    h = make_home()
    r = build(ScenarioRequest(home_id=h.home_id, measures=["cavity_wall", "heat_pump"]), h)
    assert r.bills["status"] == "ok" and r.finance["grants_gbp"] == 7500.0
    assert r.standalone["cavity_wall"]["bill_saving_gbp"] > 0 and r.standalone["heat_pump"]["net_cost_gbp"] == pytest.approx(10000.0)


# ---- C1 (D28): Monte Carlo ranges ----

from backend.app.services import uncertainty  # noqa: E402
from backend.app.services.feasibility import assess  # noqa: E402


def _unc(h, measures, seed="ab" * 8, a=HEADLINE, b=None, n=200):
    return uncertainty.run(h, b or get_baseline(h), assess(h), measures, a, seed, n=n)


def test_uncertainty_deterministic_and_ordered():
    h = make_home(glazing="single", controls="timer")
    u1, u2 = _unc(h, [M.cavity_wall, M.double_glazing]), _unc(h, [M.cavity_wall, M.double_glazing])
    assert u1["percentiles"] == u2["percentiles"]
    assert _unc(h, [M.cavity_wall], seed="cd" * 8)["percentiles"] != _unc(h, [M.cavity_wall])["percentiles"]
    for v in u1["percentiles"].values():
        if v:
            assert v["p10"] <= v["p50"] <= v["p90"]


def test_brief_range_bounds_the_glazing_draws():
    h = make_home(glazing="single")
    u = _unc(h, [M.double_glazing], n=400)
    space = 0.77 * 12000 * (1 - 0.0305)   # space share varies 0.65-0.85 in the draws, so use its bounds
    p = u["percentiles"]["gas_saving_kwh"]
    assert p["p10"] >= 0.08 * 0.65 / 0.77 * space - 1e-6 and p["p90"] <= 0.12 * 0.85 / 0.77 * space + 1e-6


def test_baseline_spread_only_when_calibrated_and_benchmark(monkeypatch):
    from backend.app.schemas.scenario import UserReading
    h = make_home()
    assert not any("baseline" in x for x in _unc(h, [M.cavity_wall])["inputs_varied"])
    monkeypatch.setattr(config, "engine_calibration", lambda: {"version": "t", "baseline_spread": {"gas_sigma_log": 0.4, "elec_sigma_log": 0.3}})
    wide = _unc(h, [M.cavity_wall])
    assert any("baseline" in x for x in wide["inputs_varied"])
    user = _unc(h, [M.cavity_wall], b=get_baseline(h, UserReading(gas_kwh=12000.0, elec_kwh=3000.0)))
    assert not any("baseline" in x for x in user["inputs_varied"])
    width = lambda u: u["percentiles"]["gas_saving_kwh"]["p90"] - u["percentiles"]["gas_saving_kwh"]["p10"]  # noqa: E731
    assert width(wide) > width(user)


def test_uncertainty_unavailable_without_baseline_and_reports_context():
    h = make_home(baseline_gas_kwh=None, gas_status="unknown_mains_gas")
    assert _unc(h, [M.cavity_wall])["status"] == "unavailable"
    u = _unc(make_home(), [M.cavity_wall])
    assert "cavity_wall" in u["household_spread_context"] and 0 <= u["prob_bill_falls"] <= 1


def test_scenario_uncertainty_optional():
    h = make_home()
    assert build(ScenarioRequest(home_id=h.home_id), h).uncertainty is None
    r = build(ScenarioRequest(home_id=h.home_id, measures=["cavity_wall"], include_uncertainty=True), h)
    assert r.uncertainty["status"] == "ok" and "uncertainty" in r.audit


# ---- C2 (D29): portfolio ranking options ----

def _poor_frame():
    import pandas as pd
    from backend.app.schemas.property import SOURCE_COLUMNS
    rows = []
    for i, (walls, roof, glazing, heating) in enumerate([
            ("Cavity wall, as built, no insulation (assumed)", "Very Poor", "single", "gas_boiler"),
            ("Solid brick, as built, no insulation (assumed)", "Poor", "single", "gas_boiler"),
            ("Cavity wall, as built, no insulation (assumed)", "Poor", "double", "gas_boiler"),
            ("Solid brick, as built, no insulation (assumed)", "Very Poor", "partial", "gas_boiler")]):
        h = make_home(home_id=f"P{i}", rating="F", sap_score=25.0, walls_rating="Very Poor", walls_description=walls,
                      roof_rating=roof, roof_description="Pitched, 25 mm loft insulation", glazing=glazing,
                      multi_glaze_pct=40.0, heating_type=heating, heating_rating="Poor", controls="none",
                      baseline_gas_kwh=18000.0 + 2000 * i, prov_baseline_gas_kwh="population_benchmark",
                      prov_baseline_elec_kwh="population_benchmark")
        d = h.model_dump()
        r = {col: d.get(field) for col, field in SOURCE_COLUMNS.items()}
        r["postcode"] = "YO10 1AA"
        rows.append(r)
    return pd.DataFrame(rows).set_index("property_id", drop=False)


def test_portfolio_rank_by_and_fabric_columns(monkeypatch):
    from backend.app.services import portfolio as pf
    monkeypatch.setattr(pf, "homes_frame", _poor_frame)
    pf._evaluate.cache_clear()
    try:
        base = pf.portfolio(top_n=10)
        assert base["summary"]["flagged_poor_or_very_poor"] == 4 and base["summary"]["rank_by"] == "improvement_potential"
        for r in base["homes"]:
            assert r["heat_pump_in_package"] and r["fabric_improvement_potential_pct"] < r["improvement_potential_pct"]
            assert r["net_cost_gbp"] == pytest.approx(r["gross_cost_gbp"] - 7500.0)
            assert r["carbon_per_pound_kg"] == pytest.approx(r["carbon_saving_kg"] / r["net_cost_gbp"])
        for key, col in pf.RANK_KEYS.items():
            vals = [r[col] for r in pf.portfolio(top_n=10, rank_by=key)["homes"]]
            assert vals == sorted(vals, reverse=True)
        with pytest.raises(ValueError):
            pf.portfolio(rank_by="nonsense")
    finally:
        pf._evaluate.cache_clear()
