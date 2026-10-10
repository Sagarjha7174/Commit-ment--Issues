"""build() with every model absent, with tiny synthetic models, and with the shipped models on the demo homes."""
import pytest

from backend.app import config
from backend.app.ml import registry
from backend.app.schemas.enums import ValueStatus
from backend.app.schemas.scenario import ScenarioRequest
from backend.app.services.scenario_builder import build
from tests.conftest import DEMO_A, DEMO_B, DEMO_C, make_home, needs_data
from tests.unit.ml_synthetic import train_tiny_sap, use_tmp_registry


def _home():
    return make_home(walls_rating="Poor", roof_rating="Poor", glazing="single", controls="timer", rating="E", sap_score=45.0,
                     postcode_outward="YO31", postcode_sector="YO31 1", habitable_rooms=5.0)


def test_build_without_any_model(monkeypatch, tmp_path):
    use_tmp_registry(monkeypatch, tmp_path)
    r = build(ScenarioRequest(home_id="T1", include_packages=False), _home())
    assert r.score_after.epc_change["status"] == "not_estimated"
    assert r.valuation.status == ValueStatus.not_estimated
    assert r.recommendation_ranking and all(x["assessor_relevance_prob"] is None for x in r.recommendation_ranking)
    assert not any(k.startswith("model_") for k in r.versions)
    registry.clear()


def test_build_with_tiny_models_is_deterministic(monkeypatch, tmp_path):
    d, f = use_tmp_registry(monkeypatch, tmp_path)
    train_tiny_sap(d, f)
    req = ScenarioRequest(home_id="T1", include_packages=False, use_modelled_epc=True)
    a, b = build(req, _home()), build(req, _home())
    assert a.scenario_id == b.scenario_id and a.score_after.parts[0].status == "modelled_epc_change"
    assert a.score_after.model_dump() == b.score_after.model_dump()
    registry.clear()


@needs_data
@pytest.mark.parametrize("home_id", [DEMO_A, DEMO_B, DEMO_C])
def test_demo_homes_with_shipped_models(home_id):
    registry.clear()
    r = build(ScenarioRequest(home_id=home_id, include_packages=False))
    assert set(r.home) & {"address", "postcode", "uprn"} == set()
    v = r.valuation
    assert v.status in (ValueStatus.ok, ValueStatus.not_estimated) and v.reason
    if v.status == ValueStatus.ok:
        assert v.low_pct <= v.mid_pct <= v.high_pct and v.provenance.value == "modelled"
        assert config.value_gate()["status"] == "enabled"
    if r.score_after is not None and registry.get("sap") is not None:
        assert r.score_after.epc_change["model_version"] == registry.get("sap").version
    if r.recommendation_ranking:
        assert [x["rank"] for x in r.recommendation_ranking] == list(range(1, len(r.recommendation_ranking) + 1))
        assert r.install_sequence
