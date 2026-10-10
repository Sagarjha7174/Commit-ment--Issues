"""M3 value model: at-sale leakage rule, target encoding, valuation abstain paths and range (tiny synthetic models)."""
import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from backend.app import config
from backend.app.ml import features as F, registry
from backend.app.ml.tuning import BASE_PARAMS
from backend.app.ml.value_data import GBM_COLS, build_value_table, lr_type_for_home, te_apply, te_oof, te_stats
from backend.app.schemas.enums import MeasureId as M, ValueStatus
from backend.app.schemas.scenario import Valuation
from backend.app.services import valuation as V
from tests.conftest import make_home
from tests.unit.ml_synthetic import synthetic_homes, train_tiny_sap, use_tmp_registry


# ---------------- leakage: features from the at-sale certificate ----------------

def _certs():
    base = {c: np.nan for c in F.FEATURE_SETS["value"]}
    old = {**base, "certificate_number": "C_OLD", "sap_score": 40.0, "log_floor_area": np.log(80), "built_form": "Detached"}
    new = {**base, "certificate_number": "C_NEW", "sap_score": 85.0, "log_floor_area": np.log(120), "built_form": "Detached"}
    return pd.DataFrame([old, new])


def _sales(cert="C_OLD", **kw):
    row = {"transaction_id": "T1", "price": 300000, "new_build": 0, "tenure": "F", "property_type": "Detached",
           "postcode_district": "YO31", "postcode_sector": "YO31 1", "property_id": "P1", "match_status": "linked",
           "sale_date": pd.Timestamp("2025-06-01"), "epc_cert_at_sale": cert, "epc_rating_at_sale_status": "observed",
           "split": "train"}
    row.update(kw)
    return pd.DataFrame([row])


def test_value_features_come_from_the_at_sale_certificate_not_the_latest():
    vt = build_value_table(_sales("C_OLD"), _certs())
    assert vt.sap_score.iloc[0] == 40.0 and vt.log_floor_area.iloc[0] == pytest.approx(np.log(80))
    vt2 = build_value_table(_sales("C_NEW"), _certs())
    assert vt2.sap_score.iloc[0] == 85.0


def test_value_table_filters_and_location_from_the_sale():
    assert build_value_table(_sales(match_status="ambiguous"), _certs()).empty
    assert build_value_table(_sales(epc_rating_at_sale_status="unavailable_no_epc_before_sale"), _certs()).empty
    vt = build_value_table(_sales(), _certs())
    assert vt.postcode_district.iloc[0] == "YO31" and vt.postcode_sector.iloc[0] == "YO31 1"
    assert vt.log_price.iloc[0] == pytest.approx(np.log(300000)) and vt.sale_month_index.iloc[0] == 5
    assert not {"paon", "saon", "street", "postcode", "sale_addr"} & set(vt.columns)


def test_value_gbm_columns_use_encoded_sector_not_raw():
    assert "postcode_sector" not in GBM_COLS and "te_sector" in GBM_COLS and "postcode_district" in GBM_COLS


# ---------------- target encoding ----------------

def test_te_smoothing_hand_computed_and_unseen_prior():
    st = te_stats(pd.Series(["a", "a", "b"]), np.array([10.0, 12.0, 4.0]), m=2)
    prior = 26 / 3
    assert st["prior"] == pytest.approx(prior)
    assert st["table"]["a"] == pytest.approx((22 + 2 * prior) / 4)
    assert te_apply(st, pd.Series(["zzz", None]))[0] == pytest.approx(prior)


def test_te_oof_never_uses_own_row():
    keys = pd.Series(["s"] * 10)
    y = np.arange(10, dtype=float)
    groups = pd.Series([f"h{i}" for i in range(10)])
    oof = te_oof(keys, y, groups)
    full = te_apply(te_stats(keys, y), keys)
    assert not np.allclose(oof, full)


def test_lr_type_for_home():
    assert lr_type_for_home("Flat", "Mid-Terrace") == "Flat/Maisonette"
    assert lr_type_for_home("House", "Enclosed End-Terrace") == "Terraced"
    assert lr_type_for_home("Bungalow", "Semi-Detached") == "Semi-detached"
    assert lr_type_for_home("House", None) is None


# ---------------- valuation service ----------------

def _train_tiny_value(models_dir):
    homes = synthetic_homes(400, seed=3)
    rows, y = [], []
    rng = np.random.default_rng(0)
    for h in homes:
        sap = float(rng.integers(30, 90))
        h = h.model_copy(update={"sap_score": sap, "postcode_outward": str(rng.choice(["YO31", "YO10"])),
                                 "postcode_sector": "YO31 1"})
        st = F.state_from_home(h)
        r = F.features(st, "value")
        r.update(F.sale_features(0, "F", "Semi-detached", "2025-06-01"))
        r["te_sector"] = 12.5
        rows.append({c: r[c] for c in GBM_COLS})
        y.append(12.0 + 0.004 * sap + 0.5 * r["log_floor_area"] + rng.normal(0, 0.05))
    df = pd.DataFrame(rows)
    cats = F.fit_categories(df, GBM_COLS)
    params = {**BASE_PARAMS, "objective": "regression", "num_leaves": 7, "min_data_in_leaf": 10, "num_threads": 1}
    b = lgb.train(params, lgb.Dataset(F.to_frame(df, GBM_COLS, cats), np.array(y)), num_boost_round=80)
    meta = {"features": list(GBM_COLS), "categories": cats, "latest_month_index": 19,
            "te_sector": {"prior": 12.5, "m": 20, "table": {"YO31 1": 12.6}, "n": {"YO31 1": 50}},
            "conformal": {"level": 0.8, "abs_log_residual_q": 0.15}, "cv_models": []}
    v = registry.save_booster("value_gbm", b, meta, models_dir=models_dir)
    registry.register("value_gbm", v, True, {}, {})
    hv = registry.save_json_model("value_hedonic", {"beta_sap_bootstrap": {"p10": 0.001, "p50": 0.002, "p90": 0.003}},
                                  models_dir=models_dir)
    registry.register("value_hedonic", hv, True, {}, {})


@pytest.fixture
def models(monkeypatch, tmp_path):
    d, f = use_tmp_registry(monkeypatch, tmp_path)
    train_tiny_sap(d, f)
    _train_tiny_value(d)
    V._cv_models.cache_clear()
    yield
    registry.clear()
    V._cv_models.cache_clear()


@pytest.fixture
def gate_open(monkeypatch):
    monkeypatch.setattr(config, "value_gate", lambda: {"status": "enabled", "coverage_check": {"result": "pass"}})


def _home(**kw):
    return make_home(walls_rating="Poor", roof_rating="Poor", sap_score=55.0, rating="D", postcode_outward="YO31",
                     postcode_sector="YO31 1", habitable_rooms=5.0, **kw)


def test_abstain_gate_closed(models, monkeypatch):
    monkeypatch.setattr(config, "value_gate", lambda: {"status": "audited", "coverage_check": {"result": "fail"}})
    v = V.estimate(_home(), [M.cavity_wall])
    assert v.status == ValueStatus.not_estimated and v.reason.startswith("value gate closed")


def test_abstain_model_missing(monkeypatch, tmp_path, gate_open):
    use_tmp_registry(monkeypatch, tmp_path)
    v = V.estimate(_home(), [M.cavity_wall])
    assert v.status == ValueStatus.not_estimated and "model missing" in v.reason
    registry.clear()


def test_abstain_no_measures(models, gate_open):
    assert "no measures" in V.estimate(_home(), []).reason


def test_abstain_sap_missing(models, gate_open):
    v = V.estimate(_home().model_copy(update={"sap_score": None}), [M.cavity_wall])
    assert v.status == ValueStatus.not_estimated and "SAP" in v.reason


def test_ok_range_ordered_and_gbp(models, gate_open):
    v = V.estimate(_home(), [M.cavity_wall, M.loft_insulation])
    assert v.status == ValueStatus.ok and v.low_pct <= v.mid_pct <= v.high_pct
    assert v.sap_change >= 0 and v.provenance.value == "modelled" and v.caveats
    assert v.value_status == ValueStatus.ok and v.current_value_low_gbp <= v.current_value_gbp <= v.current_value_high_gbp
    assert v.potential_value_low_gbp <= v.potential_value_high_gbp
    assert set(v.model_versions) == {"value_gbm", "value_hedonic", "sap"}


def test_unseen_district_drops_gbp_only(models, gate_open):
    v = V.estimate(_home().model_copy(update={"postcode_outward": "ZZ9"}), [M.cavity_wall])
    assert v.status == ValueStatus.ok and v.mid_pct is not None
    assert v.value_status == ValueStatus.not_estimated and v.current_value_gbp is None and "not seen" in v.value_reason


def test_validator_rejects_unordered_range():
    with pytest.raises(ValueError):
        Valuation(status=ValueStatus.ok, reason="x", low_pct=2.0, mid_pct=1.0, high_pct=3.0)


def test_valuation_explain(models, gate_open):
    v = V.estimate(_home(), [M.cavity_wall], explain=True)
    assert len(v.explanation) == 5 and {"feature", "value", "contribution"} <= set(v.explanation[0])
    assert V.estimate(_home(), [M.cavity_wall]).explanation is None
