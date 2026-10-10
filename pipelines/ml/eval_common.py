"""Shared evaluation of the frozen models on one split (val for M6 slices, test once in M7).

Each function rebuilds its baselines from TRAIN rows exactly as in training (deterministic) and returns a frame with
the target, model and baseline predictions and the slice columns. Only shipped models are loaded (registry).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from common import EPC_PAIRS, VALIDATION, YORK, cert_features  # noqa: E402
from backend.app.ml import features as F, metrics as M, registry  # noqa: E402
from backend.app.ml.privacy import safe_read_parquet  # noqa: E402
from backend.app.ml.value_data import build_value_table  # noqa: E402


def _report(name: str) -> dict:
    p = VALIDATION / name
    return json.loads(p.read_text()) if p.exists() else {}


# ---------------- SAP ----------------

def sap_frame(split: str) -> pd.DataFrame:
    import train_sap_model as T
    cf = cert_features()
    tr, _ = T.rows(cf)
    ok = cf.sap_target.between(1, 110) & ~(cf.floor_area_m2.notna() & ~cf.area_plausible)
    ev = cf[ok & (cf.split == split) & cf.is_latest].reset_index(drop=True)
    m = registry.get("sap")
    w = np.where(tr.is_latest, 1.0, 0.5)
    alpha = _report("ml_sap.json").get("val", {}).get("b1_ridge", {}).get("alpha", 1.0)
    b1 = T.ridge_model(alpha).fit(T._ridge_frame(tr), tr.sap_target.to_numpy(float), ridge__sample_weight=w)
    out = pd.DataFrame({"y": ev.sap_target.to_numpy(float),
                        "p_model": m.predict(ev) if m else np.nan,
                        "p_b0": T.b0_predict(T.b0_fit(tr), ev), "p_b1": b1.predict(T._ridge_frame(ev)),
                        "property_type": ev.property_type_raw.fillna("unknown"), "age_band": ev.age_band_raw.fillna("unknown"),
                        "built_form": ev.built_form_raw.fillna("unknown"), "postcode_district": ev.postcode_district.fillna("unknown")})
    out["epc_band"] = M.sap_band(out.y)
    return out


def sap_pairs(split: str) -> dict:
    import train_sap_model as T
    m = registry.get("sap")
    if m is None:
        return {}
    return T.pair_eval(m.booster, m.meta["categories"], cert_features(), pd.read_parquet(EPC_PAIRS), split)


# ---------------- value ----------------

def value_frame(split: str) -> pd.DataFrame:
    import train_value_model as T
    certs = cert_features()
    vt = build_value_table(safe_read_parquet(YORK / "sales_matched.parquet", columns=T.SALE_COLS), certs)
    tr = vt[vt.split == "train"].reset_index(drop=True)
    ev = vt[vt.split == split].reset_index(drop=True)
    tr, (ev,), _ = T.add_te(tr, [ev])
    m = registry.get("value_gbm")
    hed = T.Hedonic().fit(T.hedonic_frame(tr, certs), tr.log_price.to_numpy())
    p = np.exp(m.predict(ev)) if m else np.full(len(ev), np.nan)
    q = m.meta["conformal"]["abs_log_residual_q"] if m else np.nan
    return pd.DataFrame({"price": ev.price.to_numpy(float), "p_model": p, "p_b0": T.b0_predict(T.b0_fit(tr), ev),
                         "p_b1": np.exp(hed.predict(T.hedonic_frame(ev, certs))), "lo": p * np.exp(-q), "hi": p * np.exp(q),
                         "property_type": ev.lr_type_raw.fillna("unknown"), "tenure": np.where(ev.tenure_leasehold == 1, "L", "F"),
                         "built_form": ev.built_form.fillna("unknown"), "postcode_district": ev.postcode_district.fillna("unknown"),
                         "epc_band": M.sap_band(ev.sap_score.fillna(0))})


# ---------------- energy (NEED) ----------------

def energy_frames(split: str) -> dict[str, pd.DataFrame]:
    import train_energy_model as T
    n = T.load()
    out = {}
    for fuel in ("gas", "elec"):
        d = T.target_rows(n, fuel)
        tr, ev = d[d.split == "train"], d[d.split == split].reset_index(drop=True)
        b0 = T.b0_predict(T.b0_fit(tr), ev)
        m = registry.get(f"energy_{fuel}")
        qs = [registry.get(f"energy_{fuel}_q{q}") for q in (10, 50, 90)]
        f = pd.DataFrame({"y": ev.y.to_numpy(), "p_b0": b0["median"].to_numpy(), "b0_q10": b0.q10.to_numpy(),
                          "b0_q90": b0.q90.to_numpy(), "region": ev.need_region, "property_type": ev.need_property_type,
                          "epc_band": ev.need_epc_band, "age_band": ev.need_age_band.astype(int).astype(str)})
        X = F.to_frame(ev, T.COLS, m.meta["categories"] if m else (qs[0].meta["categories"] if qs[0] else {}))
        f["p_model"] = np.exp(m.booster.predict(X)) if m else np.nan
        if all(qs):
            qv = np.sort(np.vstack([np.exp(q.booster.predict(X)) for q in qs]), axis=0)
            f["q10"], f["q50"], f["q90"] = qv
        out[fuel] = f
        del d
    return out


# ---------------- recommender ----------------

def recommender_frame(split: str) -> pd.DataFrame:
    import train_recommender as T
    df = T.load()
    tr, ev = df[df.split == "train"], df[df.split == split].reset_index(drop=True)
    rk = registry.read_registry()["models"].get("recommender_ranking", {})
    for mm in T.MEASURE_ORDER:
        lab = T.LABEL[mm]
        ok_tr = tr[f"feas_{mm.value}"] != "infeasible"
        b1 = T.b1_predict(T.b1_fit(tr[ok_tr], lab), ev)
        ev[f"b1_{mm.value}"] = b1
        ev[f"b2_{mm.value}"] = [T.SUIT_RANK.get(s, 0) + (len(T.MEASURE_ORDER) - T.MEASURE_ORDER.index(mm)) / 100
                                for s in ev[f"suit_{mm.value}"]]
        ev[f"b0_{mm.value}"] = [1.0 + 1e-6 * T._tie(p, mm.value) for p in ev.property_id]
        model = registry.get(f"rec_{mm.value}")
        if model is not None:
            iso = model.meta["isotonic"]
            ev[f"m_{mm.value}"] = np.interp(model.predict(ev), iso["x"], iso["y"])
        else:
            ev[f"m_{mm.value}"] = b1
    ev.attrs["ranking_shipped"] = bool(rk.get("shipped"))
    return ev


def slice_table(df: pd.DataFrame, cols: list[str], err_fn, preds: list[str], min_n: int = 30) -> dict:
    """Per slice: n and error of each prediction column; flag slices whose model error > 1.5x the overall error."""
    overall = {p: err_fn(df, p) for p in preds}
    out = {"overall": {"n": int(len(df)), **{p: overall[p] for p in preds}}, "slices": {}, "flagged": []}
    for c in cols:
        out["slices"][c] = {}
        for k, g in df.groupby(c):
            if len(g) < min_n:
                continue
            e = {p: err_fn(g, p) for p in preds}
            out["slices"][c][str(k)] = {"n": int(len(g)), **e}
            if e[preds[0]] is not None and overall[preds[0]] and e[preds[0]] > 1.5 * overall[preds[0]]:
                out["flagged"].append({"slice": f"{c}={k}", "n": int(len(g)), "error": e[preds[0]], "overall": overall[preds[0]]})
    return out
