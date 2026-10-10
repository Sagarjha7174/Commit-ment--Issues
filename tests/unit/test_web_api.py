"""Web-app routes (/api, backend/app/web_api.py), the demo-home source and the LLM routes' scenario-ID alignment.

Runs on the three public demo homes (backend/app/data/demo_homes.py), so no York data is needed.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.data import demo_homes, loaders
from backend.app.main import app
from tests.conftest import DEMO_A, DEMO_B, DEMO_C, ROOT

FULL = {"include_packages": True, "include_sensitivity": True, "include_uncertainty": True}


@pytest.fixture(autouse=True)
def demo_mode(monkeypatch):
    """Force the demo-home source even on a machine that has the York build, with the LLM router wired to the real
    engine exactly as backend/app/main.py does (other test modules point it at a fake engine)."""
    from backend.app.llm.api import configure_engine
    from backend.app.llm.engine import run_request, run_scenario, set_home_source
    set_home_source(None)
    configure_engine(lambda pid, measures: run_scenario(pid, measures), request_runner=run_request)
    monkeypatch.setattr(loaders, "HOMES_TAGGED", ROOT / "data" / "absent" / "homes_tagged.parquet")
    loaders.homes_frame.cache_clear()
    from backend.app.services import portfolio as pf
    pf._evaluate.cache_clear()
    yield
    loaders.homes_frame.cache_clear()
    pf._evaluate.cache_clear()


@pytest.fixture
def client():
    return TestClient(app)


def _expect(case):
    return json.loads((ROOT / "tests" / "fixtures" / f"scenario_{case}.json").read_text())["expect"]


def test_demo_source_reproduces_hand_calc(client):
    ea = _expect("a")
    r = client.post("/api/scenario", json={"home_id": DEMO_A, "measures": ea["feasible"]}).json()
    assert r["score_before"]["total"] == ea["score_before"] and r["score_after"]["total"] == ea["score_after"]
    assert r["simulation"]["gas_saving_kwh"] == pytest.approx(ea["package_gas_saving_kwh"], rel=1e-9)
    assert r["simulation"]["elec_saving_kwh"] == pytest.approx(ea["package_elec_saving_kwh"], rel=1e-9)
    assert r["carbon"]["total_kg"] == pytest.approx(ea["carbon_saving_kg"], rel=1e-9)
    assert sorted(f["measure"] for f in r["feasibility"] if f["state"] == "infeasible") == sorted(ea["infeasible"])
    rb = client.post("/api/scenario", json={"home_id": DEMO_B}).json()
    assert rb["score_before"]["total"] == _expect("b")["score_before"]
    rc = client.post("/api/scenario", json={"home_id": DEMO_C}).json()
    assert rc["score_before"]["status"] == "unavailable" and rc["baseline"]["gas_kwh"] is None


def test_health_and_demo_list(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["data_mode"] == "demo_homes" and h["versions"]["catalogue"]
    homes = client.get("/api/demo-homes").json()
    assert [x["home_id"] for x in homes] == [DEMO_A, DEMO_B, DEMO_C]
    for x in homes:
        assert set(x) == {"home_id", "case", "display_label", "why_chosen", "rating", "property_type", "postcode_outward"}
        assert " " not in (x["postcode_outward"] or "")   # outward code only


def test_scenario_echoes_request_and_is_deterministic(client):
    body = {"home_id": DEMO_A, "measures": ["heat_pump", "cavity_wall"], **FULL}
    r1, r2 = client.post("/api/scenario", json=body).json(), client.post("/api/scenario", json=body).json()
    assert r1["scenario_id"] == r2["scenario_id"]
    r3 = client.post("/api/scenario", json={**body, "measures": ["cavity_wall", "heat_pump"]}).json()
    assert r3["scenario_id"] == r1["scenario_id"]                     # measure order does not change the id
    assert sorted(r1["request"]["measures"]) == ["cavity_wall", "heat_pump"] and r1["request"]["include_sensitivity"] is True
    assert r1["sensitivity"] is not None and r1["packages"] is not None
    assert r1["simulation"]["elec_saving_kwh"] < 0                     # heat pump: electricity rises
    assert "address" not in json.dumps(r1["home"]) and "postcode" not in r1["home"]


def test_scenario_errors(client):
    assert client.post("/api/scenario", json={"home_id": "nope"}).status_code == 404
    assert client.post("/api/scenario", json={"home_id": DEMO_A, "measures": ["nuclear"]}).status_code == 422
    assert client.post("/api/scenario", json={"home_id": DEMO_A, "surprise": 1}).status_code == 422
    assert client.post("/api/scenario", json={"home_id": DEMO_A, "user_reading": {"gas_kwh": -1}}).status_code == 422


def test_packages_budget(client):
    ps = client.post("/api/packages", json={"home_id": DEMO_A, "assumptions": {}, "user_reading": None,
                                            "budget_gbp": 5000}).json()
    assert ps["budget_gbp"] == 5000
    costs = {p["package_id"]: p["cost_gbp"] for p in ps["packages"]}
    for f in ps["featured"]:
        if f["package_id"] and f["package_id"] != "none":
            assert costs[f["package_id"]] <= 5000
    unlimited = client.post("/api/packages", json={"home_id": DEMO_A}).json()
    assert unlimited["budget_gbp"] is None
    assert client.post("/api/packages", json={"home_id": DEMO_A, "budget_gbp": -5}).status_code == 422
    assert client.post("/api/packages", json={"home_id": "nope"}).status_code == 404


def test_portfolio_and_evidence(client):
    pf = client.get("/api/portfolio?top_n=10").json()
    assert pf["data_mode"] == "demo_homes" and pf["summary"]["homes"] == 3
    assert {r["home_id"] for r in pf["homes"]} <= {DEMO_A, DEMO_B, DEMO_C}
    assert client.get("/api/portfolio?rank_by=carbon_per_pound").status_code == 200
    assert client.get("/api/portfolio?rank_by=nonsense").status_code == 422
    ev = client.get("/api/evidence").json()
    assert ev["models"]["status"] == "available"
    shipped = {m["name"]: m["shipped"] for m in ev["models"]["detail"]["models"]}
    assert shipped["sap"] is True and shipped["energy_gas"] is False
    assert ev["llm_evaluation"]["status"] == "available"
    assert ev["llm_evaluation"]["detail"]["live_llm_run"] is (ROOT / "docs/validation/llm_eval_llm.json").exists()
    assert ev["energy_prices"] and ev["grants"] and ev["finance"]
    assert ev["simulator_vs_need"]["rows"]


def test_llm_explain_matches_the_web_scenario_id(client):
    """The web app sends its full request; the explanation must be for the scenario on screen (no 409)."""
    sid = client.post("/api/scenario", json={"home_id": DEMO_A, **FULL}).json()["scenario_id"]
    body = {"property_id": DEMO_A, "measures": None, "expected_scenario_id": sid, "template_mode": True,
            "prefetch_llm": False, "assumptions": {}, "user_reading": None, **FULL}
    r = client.post("/llm/explain", json=body)
    assert r.status_code == 200 and r.json()["explanation"]["scenario_id"] == sid
    # without the request fields the server runs its default request: a different scenario, refused as stale
    r = client.post("/llm/explain", json={"property_id": DEMO_A, "expected_scenario_id": sid, "template_mode": True,
                                          "prefetch_llm": False})
    assert r.status_code == 409


def test_llm_whatif_changes_assumptions_through_the_engine(client):
    sid = client.post("/api/scenario", json={"home_id": DEMO_A, **FULL}).json()["scenario_id"]
    body = {"property_id": DEMO_A, "measures": None, "expected_scenario_id": sid, "template_mode": True,
            "question": "what if gas costs 6p per kWh", "assumptions": {}, **FULL}
    d = client.post("/llm/whatif", json=body).json()
    assert d["outcome"]["kind"] == "change_assumptions" and d["recalculated"] is True
    new_req = d["outcome"]["new_request"]
    assert new_req["assumptions"]["gas_price_p"] == 6.0 and new_req["include_sensitivity"] is True
    # applying the validated request through /api/scenario reproduces the what-if's own scenario
    assert client.post("/api/scenario", json=new_req).json()["scenario_id"] == d["scenario_id"]
    d = client.post("/llm/whatif", json={**body, "question": "remove the heat pump"}).json()
    assert d["outcome"]["kind"] == "change_measures" and "heat_pump" in d["outcome"]["removed"]


def test_demo_rows_carry_no_address_fields():
    for row in demo_homes.demo_rows():
        assert not {"address", "address1", "address2", "address3", "uprn"} & set(row)
        assert row["postcode"] is None or " " not in row["postcode"]
