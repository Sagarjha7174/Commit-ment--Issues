import json
import time
from pathlib import Path

import pytest

from backend.app.schemas.enums import MeasureId as M, ValueStatus
from backend.app.schemas.scenario import Assumptions, ScenarioRequest, ScenarioResult, UserReading
from backend.app.services.scenario_builder import build
from tests.conftest import DEMO_A, DEMO_B, DEMO_C, make_home, needs_data

FIX = Path(__file__).resolve().parents[1] / "fixtures"
TOL = 1e-6


def fixture(name):
    return json.loads((FIX / f"scenario_{name}.json").read_text())


def req(home, **kw):
    return ScenarioRequest(home_id=home.home_id, **kw)


# ---- scenario_id ----

def test_same_request_same_id_and_validates():
    h = make_home(glazing="single")
    r1, r2 = build(req(h), h), build(req(h), h)
    assert r1.scenario_id == r2.scenario_id
    ScenarioResult.model_validate(r1.model_dump())


@pytest.mark.parametrize("change", [
    {"req": {"measures": [M.loft_insulation]}},
    {"req": {"assumptions": Assumptions(heat_pump_scop=2.5)}},
    {"req": {"assumptions": Assumptions(impact_level="low")}},
    {"req": {"user_reading": UserReading(gas_kwh=9000.0)}},
    {"home": {"roof_rating": "Poor"}},
])
def test_any_change_gives_new_id(change):
    h = make_home(glazing="single")
    base = build(req(h), h).scenario_id
    h2 = make_home(glazing="single", **change.get("home", {}))
    assert build(req(h2, **change.get("req", {})), h2).scenario_id != base


def test_measure_order_in_request_does_not_change_id():
    h = make_home(glazing="single")
    a = build(req(h, measures=[M.solar_pv, M.loft_insulation]), h)
    b = build(req(h, measures=[M.loft_insulation, M.solar_pv]), h)
    assert a.scenario_id == b.scenario_id


# ---- contracts ----

def test_blocked_measure_gets_no_impact():
    h = make_home(glazing="double")
    r = build(req(h, measures=[M.double_glazing, M.loft_insulation]), h)
    assert r.measures_blocked == {"double_glazing": "infeasible: already_double_or_triple"}
    assert M.double_glazing not in r.measures_applied and "double_glazing" not in r.standalone
    assert all(s.measure != M.double_glazing for s in r.simulation.steps)


def test_no_address_in_output():
    h = make_home()
    dump = json.dumps(build(req(h), h).model_dump(mode="json"))
    for banned in ('"address"', '"postcode"', '"uprn"', '"certificate_number"'):
        assert banned not in dump


def test_user_reading_changes_baseline_and_score():
    h = make_home()
    r = build(req(h, user_reading=UserReading(gas_kwh=8000.0, elec_kwh=2500.0)), h)
    assert r.baseline.source == "user_provided" and r.baseline.gas_kwh == 8000.0
    inten = next(p for p in r.score_before.parts if p.part == "energy_intensity")
    assert inten.provenance.value == "user_provided"


def test_reconciliation_and_carbon_signs_heat_pump():
    h = make_home()
    r = build(req(h, measures=[M.heat_pump]), h)
    s = r.simulation
    assert sum(x.gas_saving_kwh for x in s.steps) == pytest.approx(s.gas_saving_kwh, abs=TOL)
    assert r.carbon.gas_kg > 0 and r.carbon.elec_kg < 0 and s.elec_saving_kwh < 0
    assert r.score_after.parts[0].status == "unchanged_epc_not_reassessed"


def test_valuation_gated():
    h = make_home()
    v = build(req(h), h).valuation
    assert v.status == ValueStatus.not_estimated and v.reason.startswith("audit pending")


def test_audit_generated_from_result():
    h = make_home(glazing="single", controls="timer")
    r = build(req(h, include_sensitivity=True), h)
    a = r.audit
    assert a["scenario_id"] == r.scenario_id and a["versions"] == r.versions
    assert {f["objective"] for f in a["featured"]} == {"lowest_cost_meeting_threshold", "largest_carbon_saving", "best_carbon_per_pound"}
    assert a["winner"]["package"]["package_id"] and "sensitivity" in a and a["main_factors"]
    assert len(a["feasibility"]) == 7 and a["packages_considered"]["count"] == len(r.packages.packages)


def test_build_under_one_second():
    h = make_home(glazing="single", controls="timer")
    build(req(h), h)
    t = time.perf_counter()
    build(req(h), h)
    assert time.perf_counter() - t < 1.0


# ---- demo homes reproduce the hand-calculated fixtures ----

@needs_data
def test_demo_a_matches_hand_calc():
    e = fixture("a")["expect"]
    r = build(ScenarioRequest(home_id=DEMO_A))
    assert r.score_before.total == e["score_before"] and r.score_before.classification == e["class_before"]
    assert r.score_before.raw_total == pytest.approx(e["score_before_raw"], abs=TOL)
    assert r.score_after.raw_total == pytest.approx(e["score_after_raw"], abs=TOL)
    assert r.score_after.total == e["score_after"]
    for k, v in e["end_uses_before"].items():
        assert getattr(r.simulation.before, k) == pytest.approx(v, abs=TOL)
    for m, v in e["standalone_gas_saving_kwh"].items():
        assert r.standalone[m]["gas_saving_kwh"] == pytest.approx(v, abs=TOL), m
    for m, v in e["standalone_elec_saving_kwh"].items():
        assert r.standalone[m]["elec_saving_kwh"] == pytest.approx(v, abs=TOL), m
    assert r.simulation.gas_saving_kwh == pytest.approx(e["package_gas_saving_kwh"], abs=TOL)
    assert r.simulation.elec_saving_kwh == pytest.approx(e["package_elec_saving_kwh"], abs=TOL)
    assert r.simulation.improvement_potential_pct == pytest.approx(e["improvement_potential_pct"], abs=TOL)
    assert r.carbon.total_kg == pytest.approx(e["carbon_saving_kg"], abs=TOL)
    assert sorted(m.value for m in r.measures_applied) == sorted(e["feasible"])


@needs_data
def test_demo_b_matches_hand_calc():
    e = fixture("b")["expect"]
    r = build(ScenarioRequest(home_id=DEMO_B))
    assert r.score_before.raw_total == pytest.approx(e["score_before_raw"], abs=TOL)
    assert r.score_before.total == e["score_before"] and r.score_before.classification == e["class_before"]
    assert r.baseline.gas_kwh == e["baseline_gas_kwh"] and r.baseline.elec_kwh == e["baseline_elec_kwh"]
    states = {f.measure.value: f.state.value for f in r.feasibility}
    assert all(states[m] == "infeasible" for m in e["infeasible"]) and all(states[m] == "feasible" for m in e["feasible"])
    rows = {x.measure.value: x for x in r.simulation.measures}
    for m, reason in e["not_estimated"].items():
        assert rows[m].status == ValueStatus.not_estimated and rows[m].reason_code == reason
    assert r.simulation.improvement_potential_status.value == e["improvement_potential_status"]
    assert r.simulation.improvement_potential_pct is None


@needs_data
def test_demo_c_matches_hand_calc():
    e = fixture("c")["expect"]
    r = build(ScenarioRequest(home_id=DEMO_C))
    assert r.score_before.status.value == e["score_status"] and r.score_before.completeness == e["completeness"]
    assert r.baseline.gas_kwh is None and r.baseline.elec_kwh is None
    assert r.simulation.improvement_potential_status.value == e["improvement_potential_status"]
    assert {f.measure.value for f in r.feasibility if f.state.value == "needs_verification"} == set(e["needs_verification"])
    assert r.score_after is None and r.carbon.total_kg is None
    assert not any("applied conditionally" in w for w in r.warnings)
