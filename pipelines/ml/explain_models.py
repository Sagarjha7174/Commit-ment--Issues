"""M6: global SHAP importance (SAP and value models) and slice metrics on VALIDATION.

Writes docs/validation/ml_shap_sap.json, ml_shap_value.json (mean |SHAP|, top 15; shap.TreeExplainer) and
ml_slices.json (val; slices whose error is > 1.5x the overall error are flagged). Test slices are added in M7.

Usage: .venv/bin/python pipelines/ml/explain_models.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap

from common import VALIDATION, cert_features, rnd, write_json  # noqa: E402
from backend.app.ml import features as F, metrics as M, registry  # noqa: E402
import eval_common as E  # noqa: E402

N_SHAP = 2000


def global_shap(name: str, X: pd.DataFrame) -> dict:
    m = registry.get(name)
    sv = shap.TreeExplainer(m.booster).shap_values(m.frame(X))
    imp = np.abs(sv).mean(axis=0)
    order = np.argsort(-imp)[:15]
    return {"model": name, "version": m.version, "n_rows": int(len(X)), "method": "shap.TreeExplainer, mean |SHAP| on val rows",
            "units": m.meta.get("target", ""), "top15": [{"feature": m.meta["features"][i], "mean_abs_shap": rnd(imp[i], 5)} for i in order]}


def mae_err(col):
    return lambda g, p: rnd(M.mae(g[col], g[p])) if g[p].notna().all() else None


def slices(split: str) -> dict:
    out = {"split": split, "rule": "flag slice if model error > 1.5 x overall model error (n >= 30)"}
    s = E.sap_frame(split)
    out["sap_mae"] = E.slice_table(s, ["property_type", "age_band", "epc_band", "built_form", "postcode_district"],
                                   mae_err("y"), ["p_model", "p_b0", "p_b1"])
    v = E.value_frame(split)
    out["value_mdape"] = E.slice_table(v, ["property_type", "tenure", "built_form", "postcode_district", "epc_band"],
                                       lambda g, p: rnd(M.mdape(g.price, g[p])), ["p_model", "p_b0", "p_b1"], min_n=20)
    en = E.energy_frames(split)
    out["energy_mae_kwh"] = {}
    for fuel, f in en.items():
        preds = ["p_model", "p_b0"] if f.p_model.notna().all() else ["p_b0"]
        out["energy_mae_kwh"][fuel] = E.slice_table(f, ["property_type", "epc_band", "age_band", "region"],
                                                    lambda g, p: rnd(M.mae(g.y, g[p]), 1), preds)
    r = E.recommender_frame(split)
    out["recommender_ndcg3"] = {}
    for c in ("property_type_raw", "age_band_raw"):
        out["recommender_ndcg3"][c] = {}
        for k, g in r.groupby(c):
            if len(g) < 100:
                continue
            out["recommender_ndcg3"][c][str(k)] = {"n": int(len(g)), **rec_ndcg(g)}
    return out


def rec_ndcg(df: pd.DataFrame) -> dict:
    import train_recommender as T
    res = {}
    for name, prefix in (("model", "m_"), ("b2", "b2_"), ("b1", "b1_")):
        groups = []
        for i in range(len(df)):
            g = [(df[f"{prefix}{m.value}"].iat[i], float(df[T.LABEL[m]].iat[i])) for m in T.MEASURE_ORDER
                 if df[f"feas_{m.value}"].iat[i] != "infeasible"]
            if g:
                groups.append(g)
        res[name] = rnd(M.ranking_metrics(groups, 3)["ndcg@3"])
    return res


def main() -> None:
    cf = cert_features()
    va = cf[(cf.split == "val") & cf.is_latest].sample(n=N_SHAP, random_state=42)
    if registry.get("sap"):
        write_json(VALIDATION / "ml_shap_sap.json", global_shap("sap", va))
    if registry.get("value_gbm"):
        import train_value_model as T
        from backend.app.ml.privacy import safe_read_parquet
        from backend.app.ml.value_data import build_value_table
        vt = build_value_table(safe_read_parquet(E.YORK / "sales_matched.parquet", columns=T.SALE_COLS), cf)
        tr, (vv,), _ = T.add_te(vt[vt.split == "train"].reset_index(drop=True), [vt[vt.split == "val"].reset_index(drop=True)])
        write_json(VALIDATION / "ml_shap_value.json", global_shap("value_gbm", vv))
    sl = slices("val")
    write_json(VALIDATION / "ml_slices.json", {"val": sl})
    for k in ("sap_mae", "value_mdape"):
        print(k, "flagged:", [f["slice"] for f in sl[k]["flagged"]])
    print("wrote ml_shap_sap.json, ml_shap_value.json, ml_slices.json")


if __name__ == "__main__":
    main()
