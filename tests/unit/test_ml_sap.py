"""M2 SAP model service: abstain paths, monotone ΔSAP, determinism, score integration (tiny synthetic model)."""
import pytest

from backend.app import config
from backend.app.ml import registry
from backend.app.schemas.enums import MeasureId as M, Provenance
from backend.app.schemas.scenario import ScenarioRequest
from backend.app.services import sap_model
from backend.app.services.scenario_builder import build
from backend.app.services.score import score_after
from tests.conftest import make_home, needs_data
from tests.unit.ml_synthetic import synthetic_homes, train_tiny_sap, use_tmp_registry

UPGRADES = [M.loft_insulation, M.cavity_wall, M.solid_wall, M.double_glazing, M.smart_thermostat, M.solar_pv]


@pytest.fixture
def no_model(monkeypatch, tmp_path):
    use_tmp_registry(monkeypatch, tmp_path)
    yield
    registry.clear()


@pytest.fixture
def tiny(monkeypatch, tmp_path):
    d, f = use_tmp_registry(monkeypatch, tmp_path)
    v = train_tiny_sap(d, f)
    yield v
    registry.clear()


def test_abstains_without_model(no_model):
    r = sap_model.sap_change(make_home(), [M.loft_insulation])
    assert r["status"] == "not_estimated" and "not available" in r["reason"] and r["sap_change"] is None
    assert sap_model.predict_sap({}) is None


def test_unshipped_model_is_not_loaded(monkeypatch, tmp_path):
    d, f = use_tmp_registry(monkeypatch, tmp_path)
    v = train_tiny_sap(d, f)
    registry.register("sap", v, False, {"val_mae_below_b0": False}, {})
    assert registry.get("sap") is None and "model_sap" not in config.versions()
    registry.clear()


def test_abstains_without_measures_or_sap(tiny):
    assert sap_model.sap_change(make_home(), [])["reason"] == "no measures applied"
    r = sap_model.sap_change(make_home(sap_score=None, roof_rating="Poor"), [M.loft_insulation])
    assert r["status"] == "not_estimated" and r["sap_change"] is not None and r["sap_after_indicative"] is None


def test_upgrades_never_lower_modelled_sap(tiny):
    for h in synthetic_homes(150, seed=7):
        for m in UPGRADES:
            r = sap_model.sap_change(h.model_copy(update={"sap_score": 50.0}), [m])
            assert r["sap_change"] >= -1e-9, (h.home_id, m)


def test_change_is_clipped_and_labelled(tiny):
    h = make_home(sap_score=99.0, walls_rating="Very Poor", roof_rating="Very Poor", glazing="single", controls="none")
    r = sap_model.sap_change(h, UPGRADES)
    assert r["status"] == "ok" and r["provenance"] == "modelled" and r["sap_after_indicative"] <= 100
    assert r["rating_before"] == "D" and r["rating_after_indicative"] in "ABCDEFG"
    assert r["model_version"] == tiny


def test_deterministic(tiny):
    h = make_home(walls_rating="Poor")
    a = sap_model.sap_change(h, [M.cavity_wall])
    registry.clear()
    assert sap_model.sap_change(h, [M.cavity_wall]) == a


def test_score_after_default_keeps_epc_part_and_attaches_change(tiny):
    h = make_home(walls_rating="Poor", roof_rating="Poor")
    s = score_after(h, [M.loft_insulation], 11000.0, 3000.0)
    part = s.parts[0]
    assert part.status == "unchanged_epc_not_reassessed" and part.sub == 60.0
    assert s.epc_change["status"] == "ok" and s.rating_after_indicative is not None


def test_score_after_modelled_epc_on_request(tiny):
    h = make_home(walls_rating="Poor", roof_rating="Poor")
    s = score_after(h, [M.loft_insulation, M.cavity_wall], 11000.0, 3000.0, use_modelled_epc=True)
    part = s.parts[0]
    assert part.status == "modelled_epc_change" and part.provenance == Provenance.modelled
    assert part.sub == pytest.approx(s.epc_change["sap_after_indicative"]) and part.sub >= 60.0


def test_score_after_without_model_unchanged(no_model):
    s = score_after(make_home(), [M.loft_insulation], 11000.0, 3000.0, use_modelled_epc=True)
    assert s.parts[0].status == "unchanged_epc_not_reassessed" and s.epc_change["status"] == "not_estimated"


def test_scenario_id_changes_with_model_version(monkeypatch, tmp_path):
    h = make_home()
    req = ScenarioRequest(home_id=h.home_id, measures=[M.loft_insulation], include_packages=False)
    use_tmp_registry(monkeypatch, tmp_path)
    sid_none = build(req, h).scenario_id
    train_tiny_sap(tmp_path / "models", tmp_path / "model_registry.json")
    r = build(req, h)
    assert r.scenario_id != sid_none and r.versions["model_sap"].startswith("sap-")
    registry.register("sap", "sap-other", True, {}, {})
    assert build(req, h).scenario_id != r.scenario_id
    registry.clear()


@needs_data
def test_shipped_sap_model_monotone_on_real_homes():
    from backend.app.data.loaders import homes_frame
    from backend.app.schemas.property import home_from_row
    registry.clear()
    if registry.get("sap") is None:
        pytest.skip("no shipped SAP model")
    for row in homes_frame().sample(n=300, random_state=1).to_dict("records"):
        h = home_from_row(row)
        for m in UPGRADES:
            r = sap_model.sap_change(h, [m])
            assert r["sap_change"] is None or r["sap_change"] >= -1e-9


def test_explain_top5_change_contributions(tiny):
    h = make_home(walls_rating="Poor", roof_rating="Poor")
    r = sap_model.sap_change(h, [M.cavity_wall], explain=True)
    ex = r["explanation"]
    assert len(ex) == 5 and ex[0]["feature"] == "walls_ord"
    assert abs(ex[0]["contribution"]) >= abs(ex[-1]["contribution"])
    assert "explanation" not in sap_model.sap_change(h, [M.cavity_wall])
