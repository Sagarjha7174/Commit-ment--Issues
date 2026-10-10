"""Evaluation metrics (pure numpy). Each is checked against hand-computed values in tests/unit/test_ml_metrics.py."""
from __future__ import annotations

from typing import Iterable, Optional

import numpy as np

SAP_BANDS = ((92, "A"), (81, "B"), (69, "C"), (55, "D"), (39, "E"), (21, "F"), (-1e9, "G"))
BAND_INDEX = {b: i for i, b in enumerate("ABCDEFG")}


def _a(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def mae(y, p) -> float:
    return float(np.mean(np.abs(_a(y) - _a(p))))


def rmse(y, p) -> float:
    return float(np.sqrt(np.mean((_a(y) - _a(p)) ** 2)))


def r2(y, p) -> float:
    y, p = _a(y), _a(p)
    ss = float(np.sum((y - y.mean()) ** 2))
    return float(1 - np.sum((y - p) ** 2) / ss) if ss > 0 else float("nan")


def within(y, p, tol: float) -> float:
    """Share of rows with |y - p| <= tol."""
    return float(np.mean(np.abs(_a(y) - _a(p)) <= tol))


def sap_band(sap) -> np.ndarray:
    """EPC band from a SAP score (A 92+, B 81-91, C 69-80, D 55-68, E 39-54, F 21-38, G 1-20)."""
    s = np.round(_a(sap))
    out = np.full(s.shape, "G", dtype=object)
    for lo, b in reversed(SAP_BANDS[:-1]):
        out[s >= lo] = b
    return out


def band_accuracy(y_sap, p_sap) -> tuple[float, float]:
    """(exact, within one band) agreement of the EPC bands implied by observed and predicted SAP."""
    yb = np.array([BAND_INDEX[b] for b in sap_band(y_sap)])
    pb = np.array([BAND_INDEX[b] for b in sap_band(p_sap)])
    return float(np.mean(yb == pb)), float(np.mean(np.abs(yb - pb) <= 1))


def pct_errors(y, p) -> np.ndarray:
    """(p - y) / y."""
    y, p = _a(y), _a(p)
    return (p - y) / y


def mdape(y, p) -> float:
    """Median absolute percentage error, as a fraction (0.1 = 10%)."""
    return float(np.median(np.abs(pct_errors(y, p))))


def ppe(y, p, tol: float) -> float:
    """Share of predictions within ±tol (fraction) of the actual value (PPE10: tol=0.10)."""
    return float(np.mean(np.abs(pct_errors(y, p)) <= tol + 1e-12))


def median_bias(y, p) -> float:
    """Median signed percentage error (fraction); positive = over-prediction."""
    return float(np.median(pct_errors(y, p)))


def pinball(y, q, alpha: float) -> float:
    """Mean pinball (quantile) loss of predictions q at level alpha."""
    d = _a(y) - _a(q)
    return float(np.mean(np.maximum(alpha * d, (alpha - 1) * d)))


def coverage(y, lo, hi) -> float:
    y = _a(y)
    return float(np.mean((y >= _a(lo)) & (y <= _a(hi))))


# ---------------- ranking ----------------

def dcg(rel: Iterable[float], k: int) -> float:
    r = _a(list(rel))[:k]
    return float(np.sum((2 ** r - 1) / np.log2(np.arange(2, r.size + 2))))


def ndcg_at_k(rel_in_pred_order: Iterable[float], k: int) -> Optional[float]:
    """NDCG@k of one ranked list; None when the list has no relevant item (excluded from means)."""
    r = list(rel_in_pred_order)
    ideal = dcg(sorted(r, reverse=True), k)
    return None if ideal == 0 else dcg(r, k) / ideal


def precision_at_1(rel_in_pred_order: Iterable[float]) -> Optional[float]:
    r = list(rel_in_pred_order)
    return None if not r or sum(r) == 0 else float(r[0] > 0)


def average_precision(rel_in_pred_order: Iterable[float]) -> Optional[float]:
    r = _a(list(rel_in_pred_order))
    if r.sum() == 0:
        return None
    hits = np.cumsum(r > 0)
    prec = hits / np.arange(1, r.size + 1)
    return float(np.sum(prec * (r > 0)) / (r > 0).sum())


def ranking_metrics(groups: list[list[tuple[float, float]]], k: int = 3) -> dict:
    """groups: per home, a list of (score, relevance). Ties keep the given order (stable sort).
    Homes without any relevant item are excluded (reported as n_excluded)."""
    nd, p1, ap = [], [], []
    for g in groups:
        order = sorted(range(len(g)), key=lambda i: -g[i][0])
        rel = [g[i][1] for i in order]
        v = ndcg_at_k(rel, k)
        if v is None:
            continue
        nd.append(v)
        p1.append(precision_at_1(rel))
        ap.append(average_precision(rel))
    n = len(nd)
    return {f"ndcg@{k}": float(np.mean(nd)) if n else None, "precision@1": float(np.mean(p1)) if n else None,
            "map": float(np.mean(ap)) if n else None, "n_homes": n, "n_excluded": len(groups) - n}


def calibration_bins(y, p, n_bins: int = 10) -> list[dict]:
    """Equal-width probability bins: mean predicted vs observed rate and count."""
    y, p = _a(y), _a(p)
    edges = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    out = []
    for b in range(n_bins):
        m = idx == b
        out.append({"bin": [float(edges[b]), float(edges[b + 1])], "n": int(m.sum()),
                    "mean_pred": float(p[m].mean()) if m.any() else None,
                    "observed": float(y[m].mean()) if m.any() else None})
    return out


def regression_summary(y, p) -> dict:
    return {"n": int(len(_a(y))), "mae": mae(y, p), "rmse": rmse(y, p), "r2": r2(y, p)}
