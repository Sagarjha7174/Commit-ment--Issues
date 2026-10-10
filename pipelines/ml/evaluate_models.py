"""M7: score the TEST split exactly once with the frozen models, against the same baselines -> docs/validation/ml_test.json.

Also: value coverage check (D10 condition 3) on test -> configs/value_gate.json; test slices -> ml_slices.json["test"].
Refuses to run if ml_test.json already exists (the test split is scored once; delete the file only to re-run on
purpose and say so in docs/EVALUATION.md).

Usage: .venv/bin/python pipelines/ml/evaluate_models.py
"""
from __future__ import annotations

import json
import time

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from common import VALIDATION, rnd, write_json  # noqa: E402
from backend.app import config  # noqa: E402
from backend.app.ml import metrics as M, registry  # noqa: E402
import eval_common as E  # noqa: E402
import explain_models as X  # noqa: E402

OUT = VALIDATION / "ml_test.json"
COV_LO, COV_HI = 0.75, 0.85


def sap_block(split: str = "test") -> dict:
    import train_sap_model as T
    s = E.sap_frame(split)
    y = s.y.to_numpy()
    return {"n": int(len(s)), "model": T.summary(y, s.p_model.to_numpy()) if registry.get("sap") else None,
            "b0": T.summary(y, s.p_b0.to_numpy()), "b1": T.summary(y, s.p_b1.to_numpy()), "pairs": E.sap_pairs(split)}


def value_block(split: str = "test") -> tuple[dict, dict]:
    import train_value_model as T
    v = E.value_frame(split)
    p = v.price.to_numpy()
    shipped = registry.get("value_gbm") is not None
    cov = float(M.coverage(p, v.lo, v.hi)) if shipped else None
    check = {"result": ("pass" if COV_LO <= cov <= COV_HI else "fail") if cov is not None else "not evaluated (no model)",
             "empirical_coverage": rnd(cov), "nominal": 0.8, "accept_range": [COV_LO, COV_HI], "n_test": int(len(v)),
             "evaluated": f"{split} split" + (", once (M7)" if split == "test" else " (dry run)")}
    return ({"n": int(len(v)), "model": T.summary(p, v.p_model.to_numpy()) if shipped else None,
             "b0": T.summary(p, v.p_b0.to_numpy()), "b1": T.summary(p, v.p_b1.to_numpy()), "coverage_check": check}, check)


def energy_block(split: str = "test") -> dict:
    import train_energy_model as T
    out = {}
    for fuel, f in E.energy_frames(split).items():
        y = f.y.to_numpy()
        york = (f.region == T.YORKSHIRE).to_numpy()
        r = {"n": int(len(f)), "n_yorkshire": int(york.sum()),
             "b0": {"overall": T.point_metrics(y, f.p_b0), "yorkshire": T.point_metrics(y[york], f.p_b0[york]),
                    "cell_quantiles": T.interval_metrics(y, f.b0_q10, f.p_b0, f.b0_q90)}}
        if f.p_model.notna().all():
            r["model"] = {"overall": T.point_metrics(y, f.p_model), "yorkshire": T.point_metrics(y[york], f.p_model[york])}
        else:
            r["model"] = "not shipped (failed its validation gate): benchmark kept"
        if "q10" in f:
            r["quantiles"] = {"overall": T.interval_metrics(y, f.q10, f.q50, f.q90),
                              "yorkshire": T.interval_metrics(y[york], f.q10[york], f.q50[york], f.q90[york])}
        out[fuel] = r
    return out


def recommender_block(split: str = "test") -> dict:
    import train_recommender as T
    r = E.recommender_frame(split)
    per = {}
    for m in T.MEASURE_ORDER:
        ok = (r[f"feas_{m.value}"] != "infeasible").to_numpy()
        y = r.loc[ok, T.LABEL[m]].to_numpy()
        e = {"n": int(ok.sum()), "positives": int(y.sum()), "shipped_classifier": registry.get(f"rec_{m.value}") is not None}
        if len(np.unique(y)) == 2:
            for name, pre in (("model", "m_"), ("b1", "b1_")):
                s = r.loc[ok, f"{pre}{m.value}"].to_numpy()
                e[name] = {"roc_auc": rnd(roc_auc_score(y, s)), "pr_auc": rnd(average_precision_score(y, s))}
        per[m.value] = e
    full = {}
    for name, pre in (("model", "m_"), ("b2_engine_order", "b2_"), ("b1_prevalence", "b1_"), ("b0_rules_random_ties", "b0_")):
        gs = []
        for i in range(len(r)):
            g = [(r[f"{pre}{m.value}"].iat[i], float(r[T.LABEL[m]].iat[i])) for m in T.MEASURE_ORDER
                 if r[f"feas_{m.value}"].iat[i] != "infeasible"]
            if g:
                gs.append(g)
        full[name] = {k: rnd(v) if isinstance(v, float) else v for k, v in M.ranking_metrics(gs, 3).items()}
    return {"n_homes": int(len(r)), "ranking": full, "per_measure": per,
            "ranking_model_shipped": r.attrs.get("ranking_shipped"),
            "label_meaning": "consistent with the EPC assessor, not feasibility"}


def update_value_gate(check: dict) -> dict:
    p = config.CONFIGS / "value_gate.json"
    g = json.loads(p.read_text())
    g["coverage_check"] = check
    ok = bool(g.get("precision_ok")) and bool(g.get("count_ok")) and check["result"] == "pass"
    g["status"] = "enabled" if ok else g.get("status", "audited")
    g["value_model_enabled_pending_coverage"] = False
    g["decision"] = ("all three D10 conditions pass: value estimate enabled" if ok else
                     "coverage check did not pass: value estimate stays gated (D10)")
    p.write_text(json.dumps(g, indent=1) + "\n")
    return g


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT.name} exists: the test split has already been scored once (M7). Not re-running.")
    t0 = time.time()
    res = {"split": "test", "scored_once": True, "frozen_models": registry.shipped_versions()}
    res["sap"] = sap_block()
    print(f"sap done [{time.time()-t0:.0f}s]")
    res["value"], check = value_block()
    res["energy"] = energy_block()
    print(f"energy done [{time.time()-t0:.0f}s]")
    res["recommender"] = recommender_block()
    g = update_value_gate(check)
    res["value_gate_after_m7"] = {"status": g["status"], "coverage_check": check}
    res["runtime_s"] = round(time.time() - t0, 1)
    write_json(OUT, res)
    sl = json.loads((VALIDATION / "ml_slices.json").read_text()) if (VALIDATION / "ml_slices.json").exists() else {}
    sl["test"] = X.slices("test")
    write_json(VALIDATION / "ml_slices.json", sl)
    print(f"wrote {OUT.name}; value coverage {check['empirical_coverage']} -> {check['result']}; value gate {g['status']} "
          f"[{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main()
