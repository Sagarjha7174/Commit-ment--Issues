"""FastAPI app: every route on the real engine (York demo homes), no address fields, template mode (no network)."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.llm import service
from backend.app.main import app
from tests.conftest import DEMO_A, DEMO_B, DEMO_C, needs_data

client = TestClient(app)
BANNED = ('"address"', '"postcode"', '"uprn"', '"certificate_number"', '"paon"', '"saon"', '"street"')


def _clean(resp):
    assert resp.status_code == 200, resp.text
    blob = json.dumps(resp.json())
    assert not any(b in blob for b in BANNED)
    return resp.json()


def test_health_without_any_key():
    j = client.get("/health").json()
    assert j["ok"] and "models" in j


@needs_data
def test_score_and_scenario_routes():
    s = _clean(client.get(f"/homes/{DEMO_A}/score"))
    assert s["score"]["total"] == 44 and s["home"]["postcode_outward"] == "YO31"
    r = _clean(client.post("/scenario", json={"home_id": DEMO_A, "include_uncertainty": True}))
    assert r["scenario_id"] and r["bills"]["status"] == "ok" and r["uncertainty"]["status"] == "ok"
    assert client.get("/homes/nope/score").status_code == 404
    assert client.post("/scenario", json={"home_id": DEMO_A, "measures": ["teleporter"]}).status_code == 422


@needs_data
@pytest.mark.parametrize("q,first", [
    ("How green is my home?", "Your Green Home Score"),
    ("What should I improve?", "Recommended improvements"),
    ("How much energy, carbon and money could I save?", "Energy savings"),
    ("Could it increase my property value?", "Property value"),
])
def test_explain_answers_the_four_core_questions(q, first):
    service.clear_cache()
    j = _clean(client.post("/explain", json={"home_id": DEMO_A, "question": q, "use_llm": False}))
    assert j["kind"] == "explain" and j["grounded"] and j["answer"].startswith(first)
    assert j["cited_values"] and all({"key", "display", "value"} <= set(c) for c in j["cited_values"])
    assert "Things to know" in j["answer"]   # caveats always included


@needs_data
@pytest.mark.parametrize("home_id", [DEMO_A, DEMO_B, DEMO_C])
def test_every_demo_home_full_report(home_id):
    j = _clean(client.post("/explain", json={"home_id": home_id, "use_llm": False, "include_payload": True}))
    assert j["grounded"] and j["payload"]["values"] and j["scenario_id"] == j["payload"]["scenario_id"]


@needs_data
def test_explain_is_cached_by_scenario():
    service.clear_cache()
    body = {"home_id": DEMO_A, "question": "How green is my home?", "use_llm": False}
    a, b = client.post("/explain", json=body).json(), client.post("/explain", json=body).json()
    assert not a["cached"] and b["cached"] and a["answer"] == b["answer"]


@needs_data
def test_whatif_routes():
    v = _clean(client.post("/whatif", json={"home_id": DEMO_A, "question": "What if electricity was on a 15p tariff?",
                                           "use_llm": False}))
    assert v["recalculated"] and v["outcome"] == "change_assumptions" and v["grounded"]
    assert v["new_request"]["assumptions"]["elec_price_p"] == 15.0 and v["scenario_id"] != v["previous_scenario_id"]
    inv = _clean(client.post("/whatif", json={"home_id": DEMO_A, "question": "What about a partial heat pump?",
                                             "use_llm": False}))
    assert inv["outcome"] == "invalid_request" and not inv["recalculated"] and inv["refusal_reason"]
    blk = _clean(client.post("/whatif", json={"home_id": DEMO_A, "question": "Add loft insulation", "use_llm": False}))
    assert blk["blocked"] == ["loft_insulation"] and not blk["recalculated"] and "not suitable" in blk["answer"]
    bud = _clean(client.post("/whatif", json={"home_id": DEMO_A, "question": "My budget is £5,000", "use_llm": False}))
    assert bud["kind"] == "advice" and "budget" in bud["answer"]


@needs_data
def test_out_of_scope_is_declined_without_calculation():
    j = _clean(client.post("/explain", json={"home_id": DEMO_A, "question": "Can I get a mortgage for this?",
                                            "use_llm": False}))
    assert j["kind"] == "out_of_scope" and not j["recalculated"] and j["cited_values"] == []


@needs_data
def test_portfolio_rank_by():
    j = _clean(client.get("/portfolio", params={"rank_by": "carbon_per_pound", "top_n": 5}))
    assert len(j["homes"]) <= 5 and "summary" in j
    assert client.get("/portfolio", params={"rank_by": "nonsense"}).status_code == 422
