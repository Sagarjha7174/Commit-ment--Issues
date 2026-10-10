"""Metrics against hand-computed values; deterministic group folds."""
import math

import numpy as np
import pandas as pd
import pytest

from backend.app.ml import metrics as m
from backend.app.ml.splits import group_fold, group_kfold


def test_regression_metrics():
    y, p = [1, 2, 3, 4], [2, 2, 2, 6]
    assert m.mae(y, p) == 1.0                          # (1+0+1+2)/4
    assert m.rmse(y, p) == pytest.approx(math.sqrt(1.5))   # (1+0+1+4)/4
    assert m.r2(y, p) == pytest.approx(1 - 6 / 5)      # SS_res 6, SS_tot 5
    assert m.within(y, p, 1) == 0.75


def test_mdape_ppe_bias():
    y, p = [100, 200, 400, 1000], [110, 180, 400, 1500]
    # % errors: +10%, -10%, 0%, +50%
    assert m.mdape(y, p) == pytest.approx(0.10)        # median of 0.1, 0.1, 0, 0.5
    assert m.ppe(y, p, 0.10) == 0.75
    assert m.ppe(y, p, 0.20) == 0.75
    assert m.median_bias(y, p) == pytest.approx(0.05)  # median of 0.1, -0.1, 0, 0.5


def test_pinball_and_coverage():
    # alpha 0.9: y-q = 2 -> 0.9*2 = 1.8; y-q = -1 -> 0.1*1 = 0.1; mean 0.95
    assert m.pinball([5, 3], [3, 4], 0.9) == pytest.approx(0.95)
    assert m.pinball([5, 3], [3, 4], 0.5) == pytest.approx(0.75)
    assert m.coverage([1, 5, 9], [0, 6, 8], [2, 7, 10]) == pytest.approx(2 / 3)


def test_sap_bands():
    assert list(m.sap_band([92, 91, 81, 80, 69, 68, 55, 54, 39, 38, 21, 20, 1])) == \
        list("ABBCCDDEEFFGG")
    assert m.band_accuracy([60, 70, 40], [62, 66, 20]) == (pytest.approx(1 / 3), pytest.approx(2 / 3))


def test_ndcg_hand_computed():
    # ranked relevances [0, 1, 1]: DCG@3 = 1/log2(3) + 1/log2(4); ideal [1, 1, 0] = 1 + 1/log2(3)
    expected = (1 / math.log2(3) + 0.5) / (1 + 1 / math.log2(3))
    assert m.ndcg_at_k([0, 1, 1], 3) == pytest.approx(expected)
    assert m.ndcg_at_k([1, 1, 0], 3) == pytest.approx(1.0)
    assert m.ndcg_at_k([0, 0], 3) is None
    assert m.ndcg_at_k([0, 0, 0, 1], 3) == 0.0


def test_precision_at_1_and_average_precision():
    assert m.precision_at_1([0, 1]) == 0.0 and m.precision_at_1([1, 0]) == 1.0
    # hits at ranks 2 and 3: (1/2 + 2/3)/2
    assert m.average_precision([0, 1, 1]) == pytest.approx((0.5 + 2 / 3) / 2)


def test_ranking_metrics_stable_ties_and_exclusion():
    groups = [[(0.9, 1), (0.1, 0)], [(0.5, 0), (0.5, 1)], [(0.3, 0)]]
    r = m.ranking_metrics(groups, k=3)
    assert r["n_homes"] == 2 and r["n_excluded"] == 1
    assert r["precision@1"] == 0.5   # tie keeps the given order -> irrelevant first in home 2


def test_calibration_bins():
    b = m.calibration_bins([0, 1, 1, 0], [0.05, 0.95, 0.91, 0.5], n_bins=10)
    assert b[0]["n"] == 1 and b[9]["n"] == 2 and b[9]["observed"] == 1.0 and b[5]["n"] == 1


def test_group_folds_deterministic_and_grouped():
    g = pd.Series(["a", "a", "b", "c", "c", "d", "e"] * 3)
    f1, f2 = group_fold(g), group_fold(g)
    assert (f1 == f2).all()
    for grp, idx in pd.Series(f1).groupby(g.values):
        assert idx.nunique() == 1
    folds = list(group_kfold(g, 5))
    assert sum(len(v) for _, v in folds) == len(g)
    for tr, va in folds:
        assert not set(g.iloc[tr]) & set(g.iloc[va])
