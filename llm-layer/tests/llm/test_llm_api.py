"""HTTP routes: template mode end to end, stale-scenario guard, what-if recompute."""

from fastapi.testclient import TestClient

from fastapi import FastAPI

import fake_engine as fe
from backend.app.llm.api import configure_engine, router

app = FastAPI()  # fake engine: fast and deterministic; the real engine is covered in test_llm_engine.py
configure_engine(fe.run)
app.include_router(router)
client = TestClient(app)


def test_explain_template_mode():
    r = client.post("/llm/explain", json={"property_id": "york-demo-poor-semi", "template_mode": True})
    assert r.status_code == 200
    body = r.json()
    assert body["explanation"]["source"] == "template"
    assert body["explanation"]["scenario_id"] == body["scenario"]["scenario_id"]
    assert any(s["id"] == "energy" for s in body["explanation"]["sections"])


def test_stale_scenario_returns_409():
    r = client.post("/llm/explain", json={"property_id": "york-demo-poor-semi", "template_mode": True,
                                          "expected_scenario_id": "sha256:old"})
    assert r.status_code == 409


def test_whatif_recomputes():
    base = fe.run("york-demo-poor-semi", ["loft_insulation"])
    r = client.post("/llm/whatif", json={"property_id": "york-demo-poor-semi", "measures": ["loft_insulation"],
                                         "question": "what if I add a heat pump", "template_mode": True,
                                         "expected_scenario_id": base["scenario_id"]})
    assert r.status_code == 200
    body = r.json()
    assert body["recalculated"] and body["scenario_id"] != base["scenario_id"]
    assert body["explanation"]["scenario_id"] == body["scenario_id"]


def test_unknown_measure_rejected_by_schema():
    r = client.post("/llm/explain", json={"property_id": "york-demo-poor-semi", "measures": ["nuclear_reactor"]})
    assert r.status_code == 422


def test_health_lists_provider_chain(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDERS", "groq,gemini")
    r = client.get("/llm/health")
    assert r.status_code == 200 and r.json()["engine_configured"]
    assert [p["provider"] for p in r.json()["providers"]] == ["groq", "gemini"]


def test_dev_app_runs_on_real_engine():
    import pytest
    pytest.importorskip("pandas")
    from dev_app import app as real_app
    c = TestClient(real_app)
    r = c.post("/llm/explain", json={"property_id": "syn-poor-semi", "template_mode": True, "prefetch_llm": False})
    assert r.status_code == 200 and r.json()["explanation"]["source"] == "template"
    assert r.json()["scenario"]["simulation"]["status"] == "ok"  # the engine's own result shape


def test_advice_routes_with_context_and_memory(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("pandas")
    from backend.app.llm import memory
    from dev_app import app as real_app
    monkeypatch.setattr(memory, "MEMORY_DIR", tmp_path)
    c = TestClient(real_app)
    r = c.post("/llm/explain", json={"property_id": "syn-poor-semi", "template_mode": True, "customer_id": "u1",
                                     "context": {"role": "tenant", "horizon": "lt2"}})
    assert r.status_code == 200 and "landlord" in r.json()["explanation"]["markdown"]
    r = c.post("/llm/whatif", json={"property_id": "syn-poor-semi", "question": "my budget is £3,000",
                                    "template_mode": True, "customer_id": "u1"})
    assert r.status_code == 200 and r.json()["advice"]["updated_context"]
    assert c.get("/llm/profile/u1").json()["budget_gbp"] == 3000
    assert len(c.get("/llm/history/u1").json()) == 2
    assert c.get("/llm/profile/..%2Fx").status_code in (404, 422)
