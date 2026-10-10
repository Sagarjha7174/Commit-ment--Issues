"""M5: retrofit relevance ranking. Labels = what the EPC assessor's software recommended on the latest certificate
(rec_*, label_only; "consistent with the EPC assessor", not "feasible"). Per measure, rows are homes where the engine
rule is not infeasible: ML only reorders feasible measures.

Baselines: B0 every feasible measure = 1 (random tie order), B1 prevalence by property type x age band (train),
B2 engine order (suitability High > Medium > Low, then catalogue order). Model: one LightGBM classifier per measure,
isotonic calibration fitted on train out-of-fold predictions. Heat pump: too few labels, rules only.
Writes docs/validation/ml_recommender.json and shipped models/rec_<measure>/.

Usage: .venv/bin/python pipelines/ml/train_recommender.py [--trials 30]
"""
from __future__ import annotations

import argparse
import hashlib
import time

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, roc_auc_score

from common import VALIDATION, cert_features, homes, rnd, write_json  # noqa: E402
from backend.app.data.loaders import homes_frame  # noqa: E402
from backend.app.ml import features as F, metrics as M, registry  # noqa: E402
from backend.app.ml.tuning import cv_fit, refit, tune  # noqa: E402
from backend.app.schemas.enums import MEASURE_ORDER, FeasibilityState, MeasureId  # noqa: E402
from backend.app.schemas.property import home_from_row  # noqa: E402
from backend.app.services.feasibility import assess  # noqa: E402

COLS = list(F.FEATURE_SETS["recommender"])
LABEL = {m: f"rec_{m.value}" for m in MEASURE_ORDER}
MIN_POSITIVES = 200
SUIT_RANK = {"High": 3, "Medium": 2, "Low": 1}


def load() -> pd.DataFrame:
    cf = cert_features()
    lat = cf[cf.is_latest].drop_duplicates("property_id").reset_index(drop=True)
    lab = homes(["property_id", *LABEL.values()])
    df = lat.merge(lab, on="property_id", how="left")
    hf = homes_frame()
    feas = {}
    for pid in df.property_id:
        items = assess(home_from_row(hf.loc[pid].to_dict()))
        feas[pid] = {i.measure: (i.state.value, i.suitability.value if i.suitability else None) for i in items}
    for m in MEASURE_ORDER:
        df[f"feas_{m.value}"] = [feas[p][m][0] for p in df.property_id]
        df[f"suit_{m.value}"] = [feas[p][m][1] for p in df.property_id]
        df[LABEL[m]] = df[LABEL[m]].fillna(0).astype(int)
    return df


def b1_fit(tr: pd.DataFrame, lab: str) -> dict:
    return {"cell": tr.groupby(["property_type_raw", "age_band_raw"])[lab].agg(["mean", "size"]),
            "type": tr.groupby("property_type_raw")[lab].mean().to_dict(), "all": float(tr[lab].mean())}


def b1_predict(b1: dict, df: pd.DataFrame) -> np.ndarray:
    c = b1["cell"]
    out = []
    for t, a in zip(df.property_type_raw, df.age_band_raw):
        if (t, a) in c.index and c.loc[(t, a), "size"] >= 30:
            out.append(float(c.loc[(t, a), "mean"]))
        else:
            out.append(b1["type"].get(t, b1["all"]))
    return np.asarray(out)


def clf_metrics(y, p, thr: float) -> dict:
    if len(np.unique(y)) < 2:
        return {"n": int(len(y)), "positives": int(y.sum())}
    return {"n": int(len(y)), "positives": int(y.sum()), "roc_auc": rnd(roc_auc_score(y, p)),
            "pr_auc": rnd(average_precision_score(y, p)), "brier": rnd(brier_score_loss(y, np.clip(p, 0, 1))),
            "f1_at_train_threshold": rnd(f1_score(y, p >= thr)), "threshold": rnd(thr)}


def best_f1_threshold(y, p) -> float:
    grid = np.unique(np.quantile(p, np.linspace(0.01, 0.99, 99)))
    return float(max(grid, key=lambda t: f1_score(y, p >= t)))


def _tie(pid: str, m: str) -> float:
    return int(hashlib.sha1(f"42:{pid}:{m}".encode()).hexdigest()[:8], 16) / 2 ** 32


def ranking(df: pd.DataFrame, scores: dict[str, np.ndarray]) -> dict:
    """NDCG@3 / P@1 / MAP per home over its non-infeasible measures (relevance = assessor recommended)."""
    out = {}
    for name, sc in scores.items():
        groups = []
        for i, pid in enumerate(df.property_id):
            g = []
            for m in MEASURE_ORDER:
                if df[f"feas_{m.value}"].iat[i] == "infeasible":
                    continue
                g.append((sc[m.value][i], float(df[LABEL[m]].iat[i])))
            if g:
                groups.append(g)
        out[name] = {k: rnd(v) if isinstance(v, float) else v for k, v in M.ranking_metrics(groups, k=3).items()}
    return out


def main(n_trials: int) -> None:
    t0 = time.time()
    df = load()
    tr, va = df[df.split == "train"].reset_index(drop=True), df[df.split == "val"].reset_index(drop=True)
    print(f"homes: train {len(tr):,}, val {len(va):,}; feasibility done [{time.time()-t0:.0f}s]")
    cats = F.fit_categories(tr, COLS)
    b1_tables = {}
    per, val_scores, models_out = {}, {"model": {}, "b0_rules_random_ties": {}, "b1_prevalence": {}, "b2_engine_order": {}}, {}
    for m in MEASURE_ORDER:
        lab = LABEL[m]
        ok_tr = (tr[f"feas_{m.value}"] != "infeasible").to_numpy()
        ok_va = (va[f"feas_{m.value}"] != "infeasible").to_numpy()
        b1 = b1_fit(tr[ok_tr], lab)
        b1_tables[m.value] = {"cell": {f"{t}|{a}": float(r["mean"]) for (t, a), r in b1["cell"].iterrows() if r["size"] >= 30},
                              "type": {str(k): float(v) for k, v in b1["type"].items()}, "all": b1["all"]}
        p_b1 = b1_predict(b1, va)
        val_scores["b1_prevalence"][m.value] = p_b1
        val_scores["b0_rules_random_ties"][m.value] = np.array([1.0 + 1e-6 * _tie(p, m.value) for p in va.property_id])
        val_scores["b2_engine_order"][m.value] = np.array(
            [SUIT_RANK.get(s, 0) + (len(MEASURE_ORDER) - MEASURE_ORDER.index(m)) / 100 for s in va[f"suit_{m.value}"]])
        y_tr, y_va = tr.loc[ok_tr, lab].to_numpy(), va.loc[ok_va, lab].to_numpy()
        rec = {"label": lab, "train_rows": int(ok_tr.sum()), "train_positives": int(y_tr.sum()),
               "val_rows": int(ok_va.sum()), "val_positives": int(y_va.sum()),
               "b0_rules": {"precision_feasible_implies_recommended": rnd(y_va.mean()) if len(y_va) else None, "recall": 1.0}}
        if y_tr.sum() < MIN_POSITIVES:
            rec.update(status="insufficient labels: rules only (B1 prevalence used for ranking)", shipped=False)
            val_scores["model"][m.value] = p_b1
            per[m.value] = rec
            registry.register(f"rec_{m.value}", None, False, {"insufficient_labels": True}, {"train_positives": int(y_tr.sum())})
            print(f"[{m.value}] insufficient labels ({int(y_tr.sum())} positives)")
            continue
        Xtr = F.to_frame(tr[ok_tr].reset_index(drop=True), COLS, cats)
        Xva = F.to_frame(va[ok_va].reset_index(drop=True), COLS, cats)
        groups = tr.loc[ok_tr, "property_id"].reset_index(drop=True)
        base = {"objective": "binary", "metric": "binary_logloss", "is_unbalance": True}
        tuned = tune(Xtr, y_tr.astype(float), None, groups, base, n_trials=n_trials, max_rounds=2000, patience=100)
        oof = cv_fit(tuned["params"], Xtr, y_tr.astype(float), None, groups, max_rounds=2000, patience=100)["oof"]
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(oof, y_tr)
        model = refit(tuned["params"], Xtr, y_tr.astype(float), None, tuned["n_rounds"])
        raw_va = model.predict(Xva)
        p_va = iso.predict(raw_va)
        thr = best_f1_threshold(y_tr, iso.predict(oof))
        mm, mb = clf_metrics(y_va, p_va, thr), clf_metrics(y_va, p_b1[ok_va], best_f1_threshold(y_tr, b1_predict(b1, tr[ok_tr])))
        shipped = mm.get("pr_auc", 0) > mb.get("pr_auc", 1)
        rec.update(model=mm, b1=mb, shipped=shipped, calibration_val=M.calibration_bins(y_va, p_va, 10),
                   tuning={"cv_logloss": rnd(tuned["cv_score"]), "n_trials": tuned["n_trials"], "n_rounds": tuned["n_rounds"]})
        full = np.full(len(va), np.nan)
        full[ok_va] = p_va
        val_scores["model"][m.value] = np.where(np.isnan(full), p_b1, full) if shipped else p_b1
        ver = None
        if shipped:
            meta = {"purpose": "recommender", "measure": m.value, "label": lab, "features": COLS, "categories": cats,
                    "params": tuned["params"], "n_rounds": tuned["n_rounds"], "threshold_f1_train": thr,
                    "isotonic": {"x": iso.X_thresholds_.tolist(), "y": iso.y_thresholds_.tolist()},
                    "features_version": F.FEATURES_VERSION, "train_rows": int(ok_tr.sum()), "val": mm,
                    "label_meaning": "consistent with the EPC assessor's recommendation, not feasibility"}
            ver = registry.save_booster(f"rec_{m.value}", model, meta)
            models_out[m.value] = ver
        registry.register(f"rec_{m.value}", ver, shipped, {"pr_auc_above_b1": shipped},
                          {"val_pr_auc": mm.get("pr_auc"), "b1_val_pr_auc": mb.get("pr_auc")})
        per[m.value] = rec
        print(f"[{m.value}] PR-AUC model {mm.get('pr_auc')} vs B1 {mb.get('pr_auc')}; ROC {mm.get('roc_auc')}; shipped {shipped} "
              f"[{time.time()-t0:.0f}s]")
    rk = ranking(va, val_scores)
    gate_rank = (rk["model"]["ndcg@3"] or 0) > (rk["b2_engine_order"]["ndcg@3"] or 0)
    write_json(VALIDATION / "ml_recommender.json", {
        "model": "recommender", "label_meaning": "agreement = consistent with the EPC assessor's software, not feasible or worth doing",
        "rows": "homes where the engine rule is not infeasible (per measure); latest certificate state",
        "gates": {"ndcg3_above_b2_engine_order": gate_rank,
                  "per_measure_pr_auc_above_b1": {k: v.get("shipped") for k, v in per.items()}},
        "ranking_val": rk, "per_measure_val": per, "shipped_versions": models_out,
        "fallback": "measures without a shipped classifier are scored by their train prevalence (B1) so scores stay comparable (D37)",
        "runtime_s": round(time.time() - t0, 1)})
    rv = registry.save_json_model("recommender_ranking", {"b1_prevalence": b1_tables, "gate_ndcg3_above_b2": gate_rank,
                                                          "use": "fallback scores for measures without a shipped classifier"})
    registry.register("recommender_ranking", rv if gate_rank else None, gate_rank, {"ndcg3_above_b2": gate_rank},
                      {"ndcg3_model": rk["model"]["ndcg@3"], "ndcg3_b2": rk["b2_engine_order"]["ndcg@3"]})
    print(f"ranking NDCG@3: model {rk['model']['ndcg@3']} | B2 {rk['b2_engine_order']['ndcg@3']} | B1 {rk['b1_prevalence']['ndcg@3']} | "
          f"B0 {rk['b0_rules_random_ties']['ndcg@3']}; gate {gate_rank} [{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=30)
    main(ap.parse_args().trials)
