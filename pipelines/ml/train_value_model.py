"""M3: property value model (log price) vs baselines; hedonic β_SAP with sector-clustered bootstrap; conformal interval.

Data: linked York sales with an observed at-sale EPC (features from the at-sale certificate, D33/D35); home split.
Writes docs/validation/ml_value.json and, when gates pass, models/value_gbm/ (model.txt + 5 CV models + meta.json)
and models/value_hedonic.json. Test is not touched (M7 runs the coverage check on test).

Usage: .venv/bin/python pipelines/ml/train_value_model.py [--trials 40]
"""
from __future__ import annotations

import argparse
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from common import VALIDATION, YORK, cert_features, rnd, write_json  # noqa: E402
from backend.app.ml import features as F, metrics as M, registry  # noqa: E402
from backend.app.ml.privacy import safe_read_parquet  # noqa: E402
from backend.app.ml.splits import SEED  # noqa: E402
from backend.app.ml.tuning import cv_fit, refit, tune  # noqa: E402
from backend.app.ml.value_data import GBM_COLS, build_value_table, te_apply, te_oof, te_stats  # noqa: E402

COLS = list(GBM_COLS)
SALE_COLS = ["transaction_id", "price", "new_build", "tenure", "property_type", "postcode_district", "postcode_sector",
             "property_id", "match_status", "sale_date", "epc_cert_at_sale", "epc_rating_at_sale_status", "split"]
CONFORMAL_LEVEL = 0.80
HEDONIC_NUM = ["log_floor_area", "habitable_rooms", "sale_month_index", "sap_score"]
HEDONIC_CAT = ["postcode_district", "lr_type", "built_form", "age_band", "tenure"]
N_BOOT = 500


# ---------------- baselines ----------------

def b0_fit(tr: pd.DataFrame) -> dict:
    def med(keys):
        return tr.groupby(keys).price.agg(["median", "size"])
    return {"sector_type": med(["postcode_sector", "lr_type"]), "district_type": med(["postcode_district", "lr_type"]),
            "district": med(["postcode_district"]), "all": float(tr.price.median())}


def b0_predict(b0: dict, df: pd.DataFrame, min_n: int = 5) -> np.ndarray:
    out = []
    for s, d, t in zip(df.postcode_sector, df.postcode_district, df.lr_type):
        for tab, key in ((b0["sector_type"], (s, t)), (b0["district_type"], (d, t)), (b0["district"], d)):
            if key in tab.index and tab.loc[key, "size"] >= min_n:
                out.append(float(tab.loc[key, "median"]))
                break
        else:
            out.append(b0["all"])
    return np.asarray(out)


# ---------------- hedonic (OLS on log price) ----------------

class Hedonic:
    """OLS on log price: one-hot categoricals (train levels, first level dropped), linear numerics (median-imputed)."""

    def fit(self, df: pd.DataFrame, y: np.ndarray):
        self.medians = {c: float(np.nanmedian(df[c])) for c in HEDONIC_NUM}
        self.levels = {c: sorted(str(v) for v in df[c].dropna().unique()) for c in HEDONIC_CAT}
        X = self.design(df)
        self.coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        self.names = self._names()
        return self

    def _names(self):
        return ["intercept", *HEDONIC_NUM, *[f"{c}={lv}" for c in HEDONIC_CAT for lv in self.levels[c][1:]]]

    def design(self, df: pd.DataFrame) -> np.ndarray:
        cols = [np.ones(len(df))]
        for c in HEDONIC_NUM:
            cols.append(pd.to_numeric(df[c], errors="coerce").fillna(self.medians[c]).to_numpy(float))
        for c in HEDONIC_CAT:
            v = df[c].astype(object).astype(str).to_numpy()
            for lv in self.levels[c][1:]:
                cols.append((v == lv).astype(float))
        return np.column_stack(cols)

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.design(df) @ self.coef

    @property
    def beta_sap(self) -> float:
        return float(self.coef[1 + HEDONIC_NUM.index("sap_score")])


def hedonic_frame(df: pd.DataFrame, certs: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    ab = certs.set_index("certificate_number").age_band_raw
    x["age_band"] = ab.reindex(df.epc_cert_at_sale).to_numpy()
    x["tenure"] = np.where(df.tenure_leasehold == 1, "L", "F")
    return x


def bootstrap_beta(df: pd.DataFrame, y: np.ndarray, n_boot: int = N_BOOT) -> dict:
    """β_SAP from resamples of postcode sectors (cluster bootstrap), seed 42."""
    rng = np.random.default_rng(SEED)
    sectors = df.postcode_sector.fillna("none").to_numpy()
    uniq = np.unique(sectors)
    idx_by = {s: np.flatnonzero(sectors == s) for s in uniq}
    betas = []
    for _ in range(n_boot):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ii = np.concatenate([idx_by[s] for s in pick])
        betas.append(Hedonic().fit(df.iloc[ii].reset_index(drop=True), y[ii]).beta_sap)
    b = np.array(betas)
    return {"n_boot": n_boot, "cluster": "postcode_sector", "n_clusters": int(len(uniq)),
            "p10": float(np.quantile(b, 0.1)), "p50": float(np.quantile(b, 0.5)), "p90": float(np.quantile(b, 0.9)),
            "mean": float(b.mean()), "share_positive": float((b > 0).mean())}


# ---------------- reports ----------------

def summary(price: np.ndarray, pred: np.ndarray) -> dict:
    return {"n": int(len(price)), "mdape": rnd(M.mdape(price, pred)), "ppe10": rnd(M.ppe(price, pred, 0.10)),
            "ppe20": rnd(M.ppe(price, pred, 0.20)), "r2_log": rnd(M.r2(np.log(price), np.log(pred))),
            "median_bias": rnd(M.median_bias(price, pred))}


def by_slice(df: pd.DataFrame, preds: dict[str, np.ndarray]) -> dict:
    out = {}
    for name, key in (("lr_type", df.lr_type_raw), ("postcode_district", df.postcode_district)):
        out[name] = {}
        for k, idx in key.groupby(key.fillna("unknown")).groups.items():
            ii = df.index.get_indexer(idx)
            if len(ii) < 20:
                continue
            out[name][str(k)] = {"n": int(len(ii)), **{m: rnd(M.mdape(df.price.to_numpy()[ii], p[ii])) for m, p in preds.items()}}
    return out


def add_te(tr: pd.DataFrame, others: list[pd.DataFrame]) -> tuple[pd.DataFrame, list[pd.DataFrame], dict]:
    """te_sector: out-of-fold on train rows, full-train statistics on other rows."""
    y = tr.log_price.to_numpy()
    tr = tr.copy()
    tr["te_sector"] = te_oof(tr.postcode_sector, y, tr.property_id)
    st = te_stats(tr.postcode_sector, y)
    outs = []
    for o in others:
        o = o.copy()
        o["te_sector"] = te_apply(st, o.postcode_sector)
        outs.append(o)
    return tr, outs, st


def make_fold_transform(tr: pd.DataFrame):
    """Inside CV: recompute te_sector from the fold's training rows only (OOF within them)."""
    sec, pid = tr.postcode_sector.reset_index(drop=True), tr.property_id.reset_index(drop=True)
    y_all = tr.log_price.to_numpy()

    def ft(Xtr, y_tr, Xva):
        itr, iva = Xtr.index.to_numpy(), Xva.index.to_numpy()
        Xtr, Xva = Xtr.copy(), Xva.copy()
        Xtr["te_sector"] = te_oof(sec.iloc[itr], y_all[itr], pid.iloc[itr])
        Xva["te_sector"] = te_apply(te_stats(sec.iloc[itr], y_all[itr]), sec.iloc[iva])
        return Xtr, Xva
    return ft


def gbm_uplift(models: list, X: pd.DataFrame, delta_sap: float) -> np.ndarray:
    X2 = X.copy()
    X2["sap_score"] = X2.sap_score + delta_sap
    return np.mean([np.exp(m.predict(X2) - m.predict(X)) - 1 for m in models], axis=0)


def main(n_trials: int) -> None:
    t0 = time.time()
    certs = cert_features()
    sales = safe_read_parquet(YORK / "sales_matched.parquet", columns=SALE_COLS)
    vt = build_value_table(sales, certs)
    vt = vt[vt.split.isin(["train", "val", "test"])].reset_index(drop=True)
    tr = vt[vt.split == "train"].reset_index(drop=True)
    va = vt[vt.split == "val"].reset_index(drop=True)
    tr, (va,), te_st = add_te(tr, [va])
    print(f"value rows: train {len(tr)}, val {len(va)} (test {int((vt.split == 'test').sum())} held for M7)")

    # baselines
    b0 = b0_fit(tr)
    p_b0 = b0_predict(b0, va)
    htr, hva = hedonic_frame(tr, certs), hedonic_frame(va, certs)
    hed = Hedonic().fit(htr, tr.log_price.to_numpy())
    p_b1 = np.exp(hed.predict(hva))
    boot = bootstrap_beta(htr, tr.log_price.to_numpy())
    print(f"B0 MdAPE {M.mdape(va.price, p_b0):.4f}; B1 hedonic MdAPE {M.mdape(va.price, p_b1):.4f}; "
          f"beta_SAP {hed.beta_sap:.5f} (p10 {boot['p10']:.5f}, p90 {boot['p90']:.5f})  [{time.time()-t0:.0f}s]")

    # GBM
    cats = F.fit_categories(tr, COLS)
    Xtr, Xva = F.to_frame(tr, COLS, cats), F.to_frame(va, COLS, cats)
    y_tr = tr.log_price.to_numpy()
    mono = [1 if c == "log_floor_area" else 0 for c in COLS]
    base = {"objective": "regression", "metric": "l1", "monotone_constraints": mono}
    ft = make_fold_transform(tr)
    tuned = tune(Xtr, y_tr, None, tr.property_id, base, n_trials=n_trials, max_rounds=3000, patience=200, fold_transform=ft)
    model = refit(tuned["params"], Xtr, y_tr, None, tuned["n_rounds"])
    cv = cv_fit({**tuned["params"]}, Xtr, y_tr, None, tr.property_id, max_rounds=3000, patience=200,
                fold_transform=ft, keep_models=True)
    spatial = cv_fit({**tuned["params"]}, Xtr, y_tr, None, tr.postcode_sector.fillna("none"), max_rounds=3000,
                     patience=200, fold_transform=ft)
    p_m = np.exp(model.predict(Xva))
    print(f"GBM val MdAPE {M.mdape(va.price, p_m):.4f} (CV l1 {tuned['cv_score']:.4f})  [{time.time()-t0:.0f}s]")

    # conformal 80% interval on val (absolute log residuals)
    res = np.abs(np.log(va.price.to_numpy()) - np.log(p_m))
    n = len(res)
    q = float(np.quantile(res, min(1.0, np.ceil((n + 1) * CONFORMAL_LEVEL) / n), method="higher"))

    # uplift illustration on val homes: +1 SAP and +10 SAP
    upl = {f"+{d}_sap": {"gbm_mean_pct": rnd(100 * float(np.mean(gbm_uplift(cv["models"], Xva, d)))),
                         "hedonic_p10_p50_p90_pct": [rnd(100 * (np.exp(boot[k] * d) - 1)) for k in ("p10", "p50", "p90")]}
           for d in (1, 10)}

    s_m, s_b0, s_b1 = summary(va.price.to_numpy(), p_m), summary(va.price.to_numpy(), p_b0), summary(va.price.to_numpy(), p_b1)
    gates = {"val_mdape_below_b0": s_m["mdape"] < s_b0["mdape"], "hedonic_beta_interval_reported": True}
    shipped = gates["val_mdape_below_b0"]
    latest_month = int(vt.sale_month_index.max())
    version = None
    if shipped:
        meta = {"purpose": "value", "features": COLS, "categories": cats, "monotone_constraints": mono,
                "params": tuned["params"], "n_rounds": tuned["n_rounds"], "target": "log(price)",
                "te_sector": te_st, "conformal": {"level": CONFORMAL_LEVEL, "abs_log_residual_q": q, "n_cal": n,
                                                  "calibration": "val split (absolute log residuals)"},
                "latest_month_index": latest_month, "features_version": F.FEATURES_VERSION,
                "train_rows": int(len(tr)), "val_metrics": s_m, "cv_models": [f"cv_{k}.txt" for k in range(len(cv["models"]))],
                "train_data_hash": registry.frame_hash(pd.concat([Xtr.astype(str), pd.Series(y_tr, name="y")], axis=1))}
        version = registry.save_booster("value_gbm", model, meta)
        for k, m in enumerate(cv["models"]):
            m.save_model(str(registry.MODELS_DIR / "value_gbm" / f"cv_{k}.txt"))
    hv = registry.save_json_model("value_hedonic", {
        "target": "log(price)", "numeric": HEDONIC_NUM, "categorical": HEDONIC_CAT, "levels": hed.levels,
        "medians": hed.medians, "coef": dict(zip(hed.names, map(float, hed.coef))), "beta_sap": hed.beta_sap,
        "beta_sap_bootstrap": boot, "train_rows": int(len(tr)),
        "interpretation": "exp(beta_sap) - 1 = price difference per SAP point, other listed factors equal (association)"})
    registry.register("value_gbm", version, shipped, gates, {"val_mdape": s_m["mdape"], "b0_val_mdape": s_b0["mdape"],
                                                             "b1_val_mdape": s_b1["mdape"]})
    registry.register("value_hedonic", hv, True, {"beta_interval_reported": True},
                      {"beta_sap": rnd(hed.beta_sap, 6), "p10": rnd(boot["p10"], 6), "p90": rnd(boot["p90"], 6)})

    # time split robustness: train-split sales <= 2025-12 -> 2026 sales of val homes (home-disjoint and later)
    early = tr[tr.sale_date <= "2025-12-31"].reset_index(drop=True)
    late = va[va.sale_date >= "2026-01-01"].reset_index(drop=True)
    early, (late,), _ = add_te(early.drop(columns="te_sector"), [late.drop(columns="te_sector")])
    m_t = refit(tuned["params"], F.to_frame(early, COLS, cats), early.log_price.to_numpy(), None, tuned["n_rounds"])
    p_t = np.exp(m_t.predict(F.to_frame(late, COLS, cats)))
    b0_t = b0_predict(b0_fit(early), late)

    report = {
        "model": "value_gbm", "version": version, "shipped": shipped, "gates": gates,
        "coverage_check": "evaluated on test in M7 (pass if 0.75 <= empirical coverage of the 80% interval <= 0.85)",
        "data": {"train": int(len(tr)), "val": int(len(va)), "test_held_out": int((vt.split == "test").sum()),
                 "filter": "match_status linked, at-sale EPC observed, Land Registry category A",
                 "features_from": "at-sale certificate (epc_cert_at_sale)"},
        "val": {"model": s_m, "b0_median_sector_type": s_b0, "b1_hedonic": s_b1},
        "cv": {"home_groupkfold_l1_log": rnd(cv["score"]), "spatial_sector_groupkfold_l1_log": rnd(spatial["score"]),
               "spatial_sector_groupkfold_mdape": rnd(M.mdape(tr.price, np.exp(spatial["oof"]))),
               "home_groupkfold_mdape": rnd(M.mdape(tr.price, np.exp(cv["oof"])))},
        "time_split": {"train": "train-split sales 2025-01..2025-12", "evaluate": "val-split sales 2026",
                       "n_train": int(len(early)), "n_eval": int(len(late)),
                       "model": summary(late.price.to_numpy(), p_t), "b0": summary(late.price.to_numpy(), b0_t)},
        "hedonic": {"beta_sap": rnd(hed.beta_sap, 6), "pct_per_sap_point": rnd(100 * (np.exp(hed.beta_sap) - 1), 4),
                    "bootstrap": {k: rnd(v, 6) if isinstance(v, float) else v for k, v in boot.items()}, "version": hv},
        "uplift_illustration_val_homes": upl,
        "conformal": {"level": CONFORMAL_LEVEL, "abs_log_residual_q": rnd(q), "val_coverage_in_sample": rnd(float(np.mean(res <= q))),
                      "interval_pct": [rnd(100 * (np.exp(-q) - 1), 2), rnd(100 * (np.exp(q) - 1), 2)]},
        "slices_val_mdape": by_slice(va, {"model": p_m, "b0": p_b0, "b1": p_b1}),
        "params": tuned["params"], "n_rounds": tuned["n_rounds"], "n_trials": tuned["n_trials"],
        "runtime_s": round(time.time() - t0, 1),
    }
    write_json(VALIDATION / "ml_value.json", report)
    print(f"val MdAPE model {s_m['mdape']} | B0 {s_b0['mdape']} | B1 {s_b1['mdape']}; PPE10 {s_m['ppe10']}; "
          f"beta_SAP {hed.beta_sap:.5f} [{boot['p10']:.5f}, {boot['p90']:.5f}]; conformal q {q:.3f}; shipped {shipped} "
          f"[{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=40)
    main(ap.parse_args().trials)
