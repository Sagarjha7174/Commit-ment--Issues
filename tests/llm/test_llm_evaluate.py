"""Evaluation harness with a mocked LLM (no network): metrics on a few held-out items, and the summary maths."""
import json
import sys
from pathlib import Path

import pytest

from backend.app.llm import client as client_mod, service
from tests.conftest import needs_data

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipelines" / "llm"))
import evaluate_llm as E  # noqa: E402

ITEMS = {i["id"]: i for i in json.loads(E.EVAL_SET.read_text())["items"]}


def test_eval_set_shape():
    items = list(ITEMS.values())
    assert 40 <= len(items) <= 60
    cats = {i["category"] for i in items}
    for c in ("core_how_green", "core_improve", "core_save", "core_value", "whatif_tariff", "whatif_partial_hp",
              "whatif_meter_reading", "whatif_budget", "whatif_drop_solar", "whatif_add_heat_pump", "missing_data",
              "conflicting_data", "infeasible_request", "electricity_rises", "value_not_estimated", "out_of_scope"):
        assert c in cats, c


@needs_data
@pytest.mark.parametrize("mode", ["mock", "template"])
def test_harness_on_a_sample(mode, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    if mode == "mock":
        monkeypatch.setattr(client_mod, "_DEFAULT_CLIENT", E.MockLLM())
    service.clear_cache()
    api = TestClient(app)
    picks = [i for i in ITEMS.values() if i["category"] in
             ("core_save", "whatif_tariff", "infeasible_request", "out_of_scope")][:6]
    rows = [E.run_item(api, it, use_llm=mode == "mock") for it in picks]
    s = E.summarise(rows)
    assert s["groundedness"] >= 0.9 and s["factual_accuracy"] >= 0.9 and s["unsupported_claim_rate"] < 0.05
    assert s["refusal_correctness"] == 1.0 and s["route_correctness"] == 1.0
    if mode == "mock":
        assert s["sources"]["llm_patched"] > 0 and s["llm_sentences_rejected_by_checker"] > 0   # invented number dropped


def test_summary_maths():
    rows = [{"id": "a", "category": "x", "numbers_total": 10, "numbers_matched": 9, "unmatched": ["5"], "sentences": 20,
             "unsupported_sentences": 1, "cited_total": 4, "cited_correct": 4, "whatif_ok": True, "passed": False,
             "checks": {"route": True, "refusal": True, "c": False}, "source": "llm", "llm_stats": {"llm_sentences": 8,
                                                                                                  "dropped": 2},
             "latency_ms": 5}]
    s = E.summarise(rows)
    assert s["groundedness"] == 0.9 and s["unsupported_claim_rate"] == 0.05 and s["factual_accuracy"] == 1.0
    assert s["llm_sentence_acceptance"] == 0.75 and not s["targets_met"]["unsupported_claim_rate"]
