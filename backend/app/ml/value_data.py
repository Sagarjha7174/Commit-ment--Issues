"""Value-model data (M3): sales joined to the certificate lodged on or before the sale date, plus target encoding.

Leakage rule: features come from `epc_cert_at_sale` (the at-sale certificate), never from the home's latest
certificate. Location: Land Registry outward code and sector of the sale. Pure functions on DataFrames.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import features as F
from .splits import group_fold

VALUE_STATE = tuple(F.FEATURE_SETS["value"])
GBM_COLS = tuple([c for c in VALUE_STATE if c != "postcode_sector"] + list(F.SALE_FEATURES) + ["te_sector"])
TE_SMOOTHING = 20.0
LR_TYPES = ("Detached", "Semi-detached", "Terraced", "Flat/Maisonette")


def build_value_table(sales: pd.DataFrame, certs: pd.DataFrame) -> pd.DataFrame:
    """sales: sales_matched (no address columns); certs: ml_cert_features (one row per certificate, derived features).
    Keeps linked sales with an observed at-sale rating; joins on epc_cert_at_sale."""
    s = sales[(sales.match_status == "linked") & (sales.epc_rating_at_sale_status == "observed")].copy()
    c = certs.set_index("certificate_number")
    missing = ~s.epc_cert_at_sale.isin(c.index)
    s = s[~missing]
    feat = c.loc[s.epc_cert_at_sale, [x for x in VALUE_STATE if x not in ("postcode_district", "postcode_sector")]]
    feat = feat.reset_index(drop=True)
    s = s.reset_index(drop=True)
    sale = pd.DataFrame([F.sale_features(nb, t, lt, d) for nb, t, lt, d in
                         zip(s.new_build, s.tenure, s.property_type, s.sale_date)])
    out = pd.concat([s[["transaction_id", "property_id", "split", "price", "sale_date", "epc_cert_at_sale",
                        "postcode_district", "postcode_sector"]], feat, sale], axis=1)
    out["log_price"] = np.log(out.price.astype(float))
    out["lr_type_raw"] = s.property_type
    out["n_dropped_no_cert"] = int(missing.sum())
    return out


# ---------------- smoothed target encoding (train rows only) ----------------

def te_stats(keys: pd.Series, y: np.ndarray, m: float = TE_SMOOTHING) -> dict:
    df = pd.DataFrame({"k": keys.astype(object).where(keys.notna(), None).to_numpy(), "y": y})
    prior = float(np.mean(y))
    g = df.dropna(subset=["k"]).groupby("k").y.agg(["sum", "size"])
    table = {str(k): float((r["sum"] + m * prior) / (r["size"] + m)) for k, r in g.iterrows()}
    return {"prior": prior, "m": m, "table": table, "n": {str(k): int(r["size"]) for k, r in g.iterrows()}}


def te_apply(stats: dict, keys: pd.Series) -> np.ndarray:
    return np.array([stats["table"].get(str(k), stats["prior"]) if k is not None and k == k else stats["prior"]
                     for k in keys.astype(object)], dtype=float)


def te_oof(keys: pd.Series, y: np.ndarray, groups: pd.Series, n_folds: int = 5) -> np.ndarray:
    """Out-of-fold encoding for training rows: a row never sees its own price (folds grouped by home)."""
    folds = group_fold(groups.reset_index(drop=True), n_folds, seed=7)
    out = np.empty(len(y))
    keys = keys.reset_index(drop=True)
    for k in range(n_folds):
        tr, va = folds != k, folds == k
        out[va] = te_apply(te_stats(keys[tr], y[tr]), keys[va])
    return out


def lr_type_for_home(property_type, built_form) -> str | None:
    """Land Registry type for a home that has no sale (assumption, D35): flats/maisonettes -> Flat/Maisonette;
    houses and bungalows by built form."""
    if property_type in ("Flat", "Maisonette"):
        return "Flat/Maisonette"
    if property_type in ("House", "Bungalow"):
        bf = (built_form or "").lower()
        if bf == "detached":
            return "Detached"
        if bf == "semi-detached":
            return "Semi-detached"
        if "terrace" in bf:
            return "Terraced"
    return None
