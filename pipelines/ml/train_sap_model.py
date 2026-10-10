"""M2: EPC SAP model (predicts the SAP score of a home state) vs baselines; counterfactual pairs; monotonicity.

Train: every certificate of TRAIN homes (latest weight 1.0, older 0.5). Validation: latest certificate of VAL homes.
Test is not touched here (M7). Writes docs/validation/ml_sap.json, ml_sap_pairs.json and, only if every gate passes,
models/sap/model.txt + meta.json and a shipped entry in configs/model_registry.json.

Usage: .venv/bin/python pipelines/ml/train_sap_model.py [--trials 60]
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from common import EPC_PAIRS, VALIDATION, cert_features, rnd, write_json  # noqa: E402
from backend.app.ml import features as F, metrics as M, registry  # noqa: E402
from backend.app.ml.splits import SEED, group_kfold  # noqa: E402
from backend.app.ml.tuning import refit, tune  # noqa: E402
from backend.app.schemas.enums import MeasureId  # noqa: E402

COLS = list(F.FEATURE_SETS["sap"])
MONO_MEASURES = (MeasureId.loft_insulation, MeasureId.cavity_wall, MeasureId.solid_wall, MeasureId.double_glazing,
                 MeasureId.smart_thermostat, MeasureId.solar_pv)


# ---------------- data ----------------

def rows(cf: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ok = cf.sap_target.between(1, 110) & ~(cf.floor_area_m2.notna() & ~cf.area_plausible)
    tr = cf[ok & (cf.split == "train")].reset_index(drop=True)
    va = cf[ok & (cf.split == "val") & cf.is_latest].reset_index(drop=True)
    return tr, va


# ---------------- baselines ----------------

def b0_fit(tr: pd.DataFrame) -> dict:
    return {"cell": tr.groupby(["property_type_raw", "age_band_raw"]).sap_target.median().to_dict(),
            "type": tr.groupby("property_type_raw").sap_target.median().to_dict(),
            "all": float(tr.sap_target.median())}


def b0_predict(b0: dict, df: pd.DataFrame) -> np.ndarray:
    out = []
    for t, a in zip(df.property_type_raw, df.age_band_raw):
        out.append(b0["cell"].get((t, a), b0["type"].get(t, b0["all"])))
    return np.asarray(out, dtype=float)


def ridge_model(alpha: float):
    cats = [c for c in COLS if c in F.CATEGORICAL]
    nums = [c for c in COLS if c not in F.CATEGORICAL]
    pre = ColumnTransformer([
        ("num", make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()), nums),
        ("cat", make_pipeline(SimpleImputer(strategy="constant", fill_value="missing"),
                              OneHotEncoder(handle_unknown="ignore", min_frequency=20)), cats)])
    return make_pipeline(pre, Ridge(alpha=alpha))


def _ridge_frame(df: pd.DataFrame) -> pd.DataFrame:
    x = df[COLS].copy()
    for c in COLS:
        if c in F.CATEGORICAL:
            x[c] = x[c].astype(object).where(x[c].notna(), "missing").astype(str)
        else:
            x[c] = pd.to_numeric(x[c], errors="coerce")
    return x


def b1_fit(tr: pd.DataFrame, w: np.ndarray) -> tuple[object, float, dict]:
    """Ridge; alpha picked by grouped 5-fold CV on train."""
    x, y = _ridge_frame(tr), tr.sap_target.to_numpy(float)
    scores = {}
    for alpha in (0.1, 1.0, 10.0, 100.0):
        maes = []
        for a, b in group_kfold(tr.property_id, 5):
            m = ridge_model(alpha).fit(x.iloc[a], y[a], ridge__sample_weight=w[a])
            maes.append(M.mae(y[b], m.predict(x.iloc[b])))
        scores[alpha] = float(np.mean(maes))
    best = min(scores, key=scores.get)
    return ridge_model(best).fit(x, y, ridge__sample_weight=w), best, scores


# ---------------- reports ----------------

def summary(y: np.ndarray, p: np.ndarray) -> dict:
    exact, one = M.band_accuracy(y, p)
    return {"n": int(len(y)), "mae": rnd(M.mae(y, p)), "rmse": rnd(M.rmse(y, p)), "r2": rnd(M.r2(y, p)),
            "within_3": rnd(M.within(y, p, 3)), "within_5": rnd(M.within(y, p, 5)),
            "band_exact": rnd(exact), "band_within_one": rnd(one)}


def slices(df: pd.DataFrame, y: np.ndarray, preds: dict[str, np.ndarray]) -> dict:
    out = {}
    band = M.sap_band(y)
    for name, key in (("property_type", df.property_type_raw.fillna("unknown")), ("age_band", df.age_band_raw.fillna("unknown")),
                      ("epc_band", pd.Series(band, index=df.index))):
        out[name] = {}
        for k, idx in key.groupby(key).groups.items():
            ii = df.index.get_indexer(idx)
            if len(ii) < 30:
                continue
            out[name][str(k)] = {"n": int(len(ii)), **{m: rnd(M.mae(y[ii], p[ii])) for m, p in preds.items()}}
    return out


def pair_eval(model, cats: dict, cf: pd.DataFrame, pairs: pd.DataFrame, split: str) -> dict:
    """Predicted ΔSAP = M(new) - M(old), both at the new certificate's lodgement year, vs observed ΔSAP."""
    by_cert = cf.set_index("certificate_number")
    tr = pairs[pairs.split == "train"]
    single = {m: tr[tr.key == f"{m}+"].delta_obs.mean() for m in ("loft", "walls", "glazing", "heating", "controls", "pv")}
    key_mean = tr.groupby("key").delta_obs.agg(["mean", "size"])
    overall = float(tr.delta_obs.mean())

    def d0(key: str) -> float:
        if key in key_mean.index and key_mean.loc[key, "size"] >= 20:
            return float(key_mean.loc[key, "mean"])
        parts = [p for p in key.split("|") if p.endswith("+") and not np.isnan(single.get(p[:-1], np.nan))]
        return float(sum(single[p[:-1]] for p in parts)) if parts else overall

    ev = pairs[pairs.split == split].reset_index(drop=True)
    old = by_cert.loc[ev.cert_old, COLS].reset_index(drop=True)
    new = by_cert.loc[ev.cert_new, COLS].reset_index(drop=True)
    old["lodgement_year"] = ev.year_new.astype(float).to_numpy()
    new["lodgement_year"] = ev.year_new.astype(float).to_numpy()
    dp = model.predict(F.to_frame(new, COLS, cats)) - model.predict(F.to_frame(old, COLS, cats))
    do = ev.delta_obs.to_numpy(float)
    base = np.array([d0(k) for k in ev.key])
    res = {"split": split, "n_pairs": int(len(ev)), "n_train_pairs_for_baseline": int(len(tr)),
           "model": {"mae": rnd(M.mae(do, dp)), "pearson_r": rnd(np.corrcoef(do, dp)[0, 1]),
                     "sign_agreement": rnd(np.mean(np.sign(do) == np.sign(np.round(dp)))), "mean_bias": rnd(np.mean(dp - do))},
           "baseline_delta0": {"mae": rnd(M.mae(do, base)), "pearson_r": rnd(np.corrcoef(do, base)[0, 1]),
                               "definition": "mean observed ΔSAP of train pairs with the same change key (n >= 20), else the sum of single-measure upgrade means, else the overall train mean"},
           "by_measure_upgrade": {}}
    for m in ("loft", "walls", "glazing", "heating", "controls", "pv"):
        mk = ev[f"up_{m}"].to_numpy()
        if mk.sum() == 0:
            continue
        res["by_measure_upgrade"][m] = {"n": int(mk.sum()), "obs_mean": rnd(do[mk].mean()), "pred_mean": rnd(dp[mk].mean()),
                                        "mean_bias": rnd((dp[mk] - do[mk]).mean()), "mae_model": rnd(M.mae(do[mk], dp[mk])),
                                        "mae_delta0": rnd(M.mae(do[mk], base[mk]))}
    return res


def monotonicity(model, cats: dict, ref_year: int, n: int = 10_000) -> dict:
    """ΔSAP >= 0 for fabric, glazing, controls and PV upgrades on n random York homes (all feasible or not)."""
    from backend.app.data.loaders import homes_frame
    from backend.app.schemas.property import home_from_row
    hf = homes_frame().sample(n=n, random_state=SEED)
    homes = [home_from_row(r) for r in hf.to_dict("records")]
    before = F.to_frame([F.features(F.state_from_home(h), "sap", ref_year) for h in homes], COLS, cats)
    pb = model.predict(before)
    out = {"n_homes": n}
    for m in MONO_MEASURES:
        after = F.to_frame([F.after_features(h, [m], "sap", ref_year) for h in homes], COLS, cats)
        d = model.predict(after) - pb
        out[m.value] = {"min_delta": rnd(float(d.min()), 6), "n_negative": int((d < -1e-9).sum()),
                        "mean_delta": rnd(float(d.mean())), "share_positive": rnd(float((d > 1e-9).mean()))}
    after = F.to_frame([F.after_features(h, [MeasureId.heat_pump], "sap", ref_year) for h in homes], COLS, cats)
    d = model.predict(after) - pb
    out["heat_pump_unconstrained"] = {"mean_delta": rnd(float(d.mean())), "share_negative": rnd(float((d < 0).mean()))}
    out["passed"] = all(out[m.value]["n_negative"] == 0 for m in MONO_MEASURES)
    return out


def main(n_trials: int) -> None:
    t0 = time.time()
    cf = cert_features()
    tr, va = rows(cf)
    w = np.where(tr.is_latest, 1.0, 0.5)
    y_tr, y_va = tr.sap_target.to_numpy(float), va.sap_target.to_numpy(float)
    cats = F.fit_categories(tr, COLS)
    Xtr, Xva = F.to_frame(tr, COLS, cats), F.to_frame(va, COLS, cats)
    ref_year = int(tr.lodgement_year.max())
    print(f"train rows {len(tr):,} ({tr.property_id.nunique():,} homes); val {len(va):,}; reference year {ref_year}")

    b0 = b0_fit(tr)
    p_b0 = b0_predict(b0, va)
    b1, alpha, alpha_scores = b1_fit(tr, w)
    p_b1 = b1.predict(_ridge_frame(va))
    print(f"B0 val MAE {M.mae(y_va, p_b0):.3f}; B1 (alpha {alpha}) val MAE {M.mae(y_va, p_b1):.3f}  [{time.time()-t0:.0f}s]")

    base = {"objective": "regression", "metric": "l1", "monotone_constraints": F.monotone_constraints("sap"),
            "monotone_constraints_method": "basic"}
    tuned = tune(Xtr, y_tr, w, tr.property_id, base, n_trials=n_trials, max_rounds=4000, patience=200)
    print(f"tuned: CV MAE {tuned['cv_score']:.3f}, rounds {tuned['n_rounds']}, trials {tuned['n_complete']}/{tuned['n_trials']} complete  [{time.time()-t0:.0f}s]")
    model = refit(tuned["params"], Xtr, y_tr, w, tuned["n_rounds"])
    p_m = model.predict(Xva)

    s_m, s_b0, s_b1 = summary(y_va, p_m), summary(y_va, p_b0), summary(y_va, p_b1)
    pairs = pair_eval(model, cats, cf, pd.read_parquet(EPC_PAIRS), "val")
    mono = monotonicity(model, cats, ref_year)
    gates = {
        "val_mae_below_b0": s_m["mae"] < s_b0["mae"],
        "val_mae_below_b1": s_m["mae"] < s_b1["mae"],
        "monotonicity": mono["passed"],
        "pairs_mae_below_delta0": pairs["model"]["mae"] < pairs["baseline_delta0"]["mae"],
        "r2_sanity_ge_0.75": s_m["r2"] >= 0.75,
    }
    shipped = all(gates.values())
    meta = {"purpose": "sap", "features": COLS, "categories": cats, "monotone_constraints": base["monotone_constraints"],
            "params": tuned["params"], "n_rounds": tuned["n_rounds"], "reference_year": ref_year,
            "features_version": F.FEATURES_VERSION, "train_rows": int(len(tr)), "train_homes": int(tr.property_id.nunique()),
            "train_data_hash": registry.frame_hash(pd.concat([Xtr.astype(str), pd.Series(y_tr, name="y")], axis=1)),
            "weights": "latest certificate 1.0, older 0.5", "val_metrics": s_m, "target": "c_sap_score (EPC SAP 1-110)"}
    version = registry.save_booster("sap", model, meta) if shipped else None
    registry.register("sap", version, shipped, gates, {"val_mae": s_m["mae"], "b0_val_mae": s_b0["mae"], "b1_val_mae": s_b1["mae"],
                                                      "pairs_mae": pairs["model"]["mae"], "delta0_mae": pairs["baseline_delta0"]["mae"]})
    report = {
        "model": "sap", "version": version, "shipped": shipped, "gates": gates, "split": "val (latest certificate of val homes)",
        "train": {"rows": int(len(tr)), "homes": int(tr.property_id.nunique()), "cv_mae_tuned": rnd(tuned["cv_score"]),
                  "n_trials": tuned["n_trials"], "n_complete_trials": tuned["n_complete"], "n_rounds": tuned["n_rounds"]},
        "val": {"model": s_m, "b0_median_type_x_age": s_b0, "b1_ridge": {**s_b1, "alpha": alpha, "alpha_cv_mae": alpha_scores}},
        "slices_val_mae": slices(va, y_va, {"model": p_m, "b0": p_b0, "b1": p_b1}),
        "monotonicity": mono, "params": tuned["params"], "reference_year": ref_year,
        "runtime_s": round(time.time() - t0, 1),
    }
    write_json(VALIDATION / "ml_sap.json", report)
    write_json(VALIDATION / "ml_sap_pairs.json", pairs)
    print(f"val MAE model {s_m['mae']} | B0 {s_b0['mae']} | B1 {s_b1['mae']}; R2 {s_m['r2']}; pairs MAE {pairs['model']['mae']} "
          f"vs Δ0 {pairs['baseline_delta0']['mae']}; monotone {mono['passed']}; shipped {shipped} [{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=60)
    main(ap.parse_args().trials)
