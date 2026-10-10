"""M4: NEED energy model (annual gas / electricity) vs the engine's cell-median benchmark; quantile models.

Data: need_4m (its own split), rows with an EPC band (York homes always have one; the engine's benchmarks also drop
missing bands). Features: only what York homes share with NEED (FEATURE_SETS["energy_york"]); NEED-only fields
(council tax band, IMD, insulation scheme flags) are not used. Targets: metered gas of gas-heated homes; metered
electricity. B0 = median per region x main fuel x type x EPC band x area band (L1 -> L2 -> L3, >= 30 homes), train only.
D21 area scaling is a no-op on NEED rows (one representative area per band).

Writes docs/validation/ml_energy.json, configs/model_switch.json and, when gates pass, models/energy_*.
Usage: .venv/bin/python pipelines/ml/train_energy_model.py [--trials 40]
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from common import PROC, VALIDATION, rnd, write_json  # noqa: E402
from backend.app import config  # noqa: E402
from backend.app.ml import features as F, metrics as M, registry  # noqa: E402
from backend.app.ml.splits import SEED  # noqa: E402
from backend.app.ml.tuning import refit, tune  # noqa: E402

COLS = list(F.FEATURE_SETS["energy_york"])
NEED_TO_FEATURE = {"property_type": "need_property_type", "age_band_code": "need_age_band",
                   "floor_area_band_code": "need_floor_area_band", "epc_band": "need_epc_band",
                   "main_heat_gas": "need_main_heat_gas", "solar_pv": "solar_pv", "region_code": "need_region"}
YORKSHIRE = "E12000003"
LEVELS = (("L1", ["need_region", "fuel_key", "need_property_type", "need_epc_band", "need_floor_area_band"]),
          ("L2", ["need_region", "fuel_key", "need_property_type", "need_epc_band"]),
          ("L3", ["need_region", "fuel_key", "need_epc_band"]))
MIN_N = 30
QUANTILES = (0.1, 0.5, 0.9)
SUBSAMPLE = 500_000


def load() -> pd.DataFrame:
    cols = [*NEED_TO_FEATURE, "gas_status", "gas_kwh", "elec_status", "elec_kwh", "split", "property_id"]
    p = PROC / "need_4m.parquet"
    if not p.exists():
        p = PROC / "need_50k.parquet"
    n = pd.read_parquet(p, columns=cols)
    n = n[n.epc_band.notna()].rename(columns=NEED_TO_FEATURE).reset_index(drop=True)
    n["need_main_heat_gas"] = n.need_main_heat_gas.astype(float)
    n["solar_pv"] = n.solar_pv.astype(float)
    n["need_age_band"] = n.need_age_band.astype(float)
    n["need_floor_area_band"] = n.need_floor_area_band.astype(float)
    n["fuel_key"] = n.need_main_heat_gas.astype(int)
    n.attrs["source"] = p.name
    return n


def target_rows(n: pd.DataFrame, fuel: str) -> pd.DataFrame:
    if fuel == "gas":
        m = (n.gas_status == "metered") & (n.need_main_heat_gas == 1) & (n.gas_kwh > 0)
    else:
        m = (n.elec_status == "metered") & (n.elec_kwh > 0)
    d = n[m].copy()
    d["y"] = d[f"{fuel}_kwh"].astype(float)
    return d.reset_index(drop=True)


# ---------------- B0: the engine's benchmark cells, recomputed on train ----------------

def b0_fit(tr: pd.DataFrame) -> dict:
    out = {}
    for lvl, keys in LEVELS:
        g = tr.groupby(keys).y
        t = pd.DataFrame({"q10": g.quantile(0.1), "median": g.median(), "q90": g.quantile(0.9), "n": g.size()})
        out[lvl] = t[t.n >= MIN_N].reset_index()
    return out


def b0_predict(b0: dict, df: pd.DataFrame) -> pd.DataFrame:
    res = pd.DataFrame(index=df.index, columns=["q10", "median", "q90", "level"], dtype=object)
    for lvl, keys in LEVELS:
        j = df[keys].merge(b0[lvl], on=keys, how="left")
        j.index = df.index
        fill = res["median"].isna() & j["median"].notna()
        res.loc[fill, ["q10", "median", "q90"]] = j.loc[fill, ["q10", "median", "q90"]].to_numpy()
        res.loc[fill, "level"] = lvl
    for c in ("q10", "median", "q90"):
        res[c] = res[c].astype(float)
    return res


def stratified_sample(tr: pd.DataFrame, n: int) -> pd.DataFrame:
    if len(tr) <= n:
        return tr
    frac = n / len(tr)
    return tr.groupby(["need_region", "need_epc_band"], group_keys=False).sample(frac=frac, random_state=SEED)


def point_metrics(y, p) -> dict:
    return {"n": int(len(y)), "mae_kwh": rnd(M.mae(y, p), 1), "mdape": rnd(M.mdape(y, p)), "r2_log": rnd(M.r2(np.log(y), np.log(p)))}


def interval_metrics(y, q10, q50, q90) -> dict:
    return {"coverage_p10_p90": rnd(M.coverage(y, q10, q90)),
            "pinball_kwh": {"0.1": rnd(M.pinball(y, q10, 0.1), 1), "0.5": rnd(M.pinball(y, q50, 0.5), 1),
                            "0.9": rnd(M.pinball(y, q90, 0.9), 1)},
            "mean_pinball_kwh": rnd(np.mean([M.pinball(y, q10, 0.1), M.pinball(y, q50, 0.5), M.pinball(y, q90, 0.9)]), 1)}


def run_fuel(n: pd.DataFrame, fuel: str, n_trials: int, t0: float) -> dict:
    d = target_rows(n, fuel)
    tr, va = d[d.split == "train"].reset_index(drop=True), d[d.split == "val"].reset_index(drop=True)
    yk = va.y.to_numpy()
    york = (va.need_region == YORKSHIRE).to_numpy()
    b0 = b0_predict(b0_fit(tr), va)
    has_b0 = b0["median"].notna().to_numpy()
    print(f"[{fuel}] train {len(tr):,}, val {len(va):,} (Yorkshire {york.sum():,}); B0 coverage {has_b0.mean():.4f}")

    cats = F.fit_categories(tr, COLS)
    sub = stratified_sample(tr, SUBSAMPLE).reset_index(drop=True)
    Xs = F.to_frame(sub, COLS, cats)
    tuned = tune(Xs, np.log(sub.y.to_numpy()), None, sub.property_id, {"objective": "regression", "metric": "l1"},
                 n_trials=n_trials, n_folds=3, max_rounds=2000, patience=100)
    print(f"[{fuel}] tuned CV l1(log) {tuned['cv_score']:.4f}, rounds {tuned['n_rounds']}  [{time.time()-t0:.0f}s]")
    Xtr, Xva = F.to_frame(tr, COLS, cats), F.to_frame(va, COLS, cats)
    ylog = np.log(tr.y.to_numpy())

    cands = {}
    for obj in ("regression", "huber", "regression_l1"):
        b = refit({**tuned["params"], "objective": obj, **({"alpha": 0.9} if obj == "huber" else {})}, Xtr, ylog, None, tuned["n_rounds"])
        p = np.exp(b.predict(Xva))
        cands[obj] = (b, p, M.mae(yk, p))
        print(f"[{fuel}]   objective {obj}: val MAE {cands[obj][2]:.1f}  [{time.time()-t0:.0f}s]")
    best_obj = min(cands, key=lambda k: cands[k][2])
    model, p_m, _ = cands[best_obj]

    qmodels, qp = {}, {}
    for a in QUANTILES:
        qmodels[a] = refit({**tuned["params"], "objective": "quantile", "alpha": a, "metric": "quantile"}, Xtr, ylog, None,
                           tuned["n_rounds"])
        qp[a] = np.exp(qmodels[a].predict(Xva))
    qs = np.sort(np.vstack([qp[a] for a in QUANTILES]), axis=0)   # no crossing

    # compare on rows where B0 has a cell (all, in practice)
    m_all, b_all = point_metrics(yk[has_b0], p_m[has_b0]), point_metrics(yk[has_b0], b0["median"].to_numpy()[has_b0])
    yy = has_b0 & york
    m_y, b_y = point_metrics(yk[yy], p_m[yy]), point_metrics(yk[yy], b0["median"].to_numpy()[yy])
    qi_all = interval_metrics(yk[has_b0], *(qs[i][has_b0] for i in range(3)))
    bi_all = interval_metrics(yk[has_b0], *(b0[c].to_numpy()[has_b0] for c in ("q10", "median", "q90")))
    qi_y = interval_metrics(yk[yy], *(qs[i][yy] for i in range(3)))
    bi_y = interval_metrics(yk[yy], *(b0[c].to_numpy()[yy] for c in ("q10", "median", "q90")))
    gates = {"mae_at_least_2pct_below_b0_overall": m_all["mae_kwh"] <= 0.98 * b_all["mae_kwh"],
             "mae_not_worse_on_yorkshire": m_y["mae_kwh"] <= b_y["mae_kwh"]}
    point_ok = all(gates.values())
    q_ok = qi_all["mean_pinball_kwh"] < bi_all["mean_pinball_kwh"] and qi_y["mean_pinball_kwh"] <= bi_y["mean_pinball_kwh"]
    gates["quantiles_mean_pinball_below_b0_cell_quantiles"] = q_ok

    meta = {"purpose": "energy_york", "fuel": fuel, "features": COLS, "categories": cats, "target": f"log {fuel} kWh/yr (NEED)",
            "params": tuned["params"], "n_rounds": tuned["n_rounds"], "objective": best_obj, "train_rows": int(len(tr)),
            "source": n.attrs.get("source"), "features_version": F.FEATURES_VERSION,
            "train_data_hash": registry.frame_hash(pd.concat([Xs.astype(str), pd.Series(np.log(sub.y.to_numpy()), name="y")], axis=1))}
    ver = registry.save_booster(f"energy_{fuel}", model, {**meta, "val": m_all}) if point_ok else None
    registry.register(f"energy_{fuel}", ver, point_ok, gates, {"val_mae": m_all["mae_kwh"], "b0_val_mae": b_all["mae_kwh"],
                                                               "york_val_mae": m_y["mae_kwh"], "york_b0_val_mae": b_y["mae_kwh"]})
    qver = {}
    for a in QUANTILES:
        name = f"energy_{fuel}_q{int(a * 100)}"
        qver[name] = registry.save_booster(name, qmodels[a], {**meta, "objective": "quantile", "alpha": a}) if q_ok else None
        registry.register(name, qver[name], q_ok, {"quantiles_mean_pinball_below_b0_cell_quantiles": q_ok},
                          {"mean_pinball_kwh": qi_all["mean_pinball_kwh"], "b0_mean_pinball_kwh": bi_all["mean_pinball_kwh"]})
    return {"fuel": fuel, "shipped_point": point_ok, "shipped_quantiles": q_ok, "version": ver, "quantile_versions": qver,
            "gates": gates, "objective_selected_on_val": best_obj,
            "objective_val_mae": {k: rnd(v[2], 1) for k, v in cands.items()},
            "data": {"train": int(len(tr)), "val": int(len(va)), "val_yorkshire": int(york.sum()),
                     "val_rows_with_b0_cell": int(has_b0.sum()), "b0_level_used": b0.level.value_counts().to_dict()},
            "val_overall": {"model": m_all, "b0": b_all, "model_quantiles": qi_all, "b0_cell_quantiles": bi_all},
            "val_yorkshire": {"model": m_y, "b0": b_y, "model_quantiles": qi_y, "b0_cell_quantiles": bi_y},
            "tuning": {"n_trials": tuned["n_trials"], "n_complete": tuned["n_complete"], "cv_l1_log": rnd(tuned["cv_score"]),
                       "subsample_rows": int(len(sub)), "folds": 3}, "params": tuned["params"], "n_rounds": tuned["n_rounds"]}


def main(n_trials: int) -> None:
    t0 = time.time()
    n = load()
    print(f"NEED rows with EPC band: {len(n):,} ({n.attrs['source']})")
    res = {f: run_fuel(n, f, n_trials, t0) for f in ("gas", "elec")}
    both = res["gas"]["shipped_point"] and res["elec"]["shipped_point"]
    switch = {"use_model_baseline": both, "beat_benchmark": both,
              "model_version": {f: res[f]["version"] for f in res},
              "per_fuel_gate": {f: res[f]["shipped_point"] for f in res},
              "val_mae": {f: res[f]["val_overall"]["model"]["mae_kwh"] for f in res},
              "benchmark_val_mae": {f: res[f]["val_overall"]["b0"]["mae_kwh"] for f in res},
              "rule": "on only if both fuels beat the benchmark MAE by >= 2% overall and are not worse on Yorkshire (D36)"}
    (config.CONFIGS / "model_switch.json").write_text(json.dumps(switch, indent=1) + "\n")
    write_json(VALIDATION / "ml_energy.json", {
        "model": "energy", "scope": "NEED homes (England and Wales); transfer to York EPC homes is unproven (LABELS.md 1)",
        "features": COLS, "excluded_features": "council tax band, IMD, insulation scheme flags (not available for York homes)",
        "fuels": res, "model_switch": switch, "runtime_s": round(time.time() - t0, 1)})
    for f in res:
        r = res[f]
        print(f"[{f}] val MAE model {r['val_overall']['model']['mae_kwh']} vs B0 {r['val_overall']['b0']['mae_kwh']}; "
              f"Yorkshire {r['val_yorkshire']['model']['mae_kwh']} vs {r['val_yorkshire']['b0']['mae_kwh']}; "
              f"P10-P90 coverage {r['val_overall']['model_quantiles']['coverage_p10_p90']}; point {r['shipped_point']}, "
              f"quantiles {r['shipped_quantiles']}")
    print(f"model_switch use_model_baseline={both} [{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=40)
    main(ap.parse_args().trials)
