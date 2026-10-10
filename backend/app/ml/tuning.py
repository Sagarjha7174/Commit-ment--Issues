"""Deterministic LightGBM training and Optuna (TPE) tuning with grouped CV on train rows only.

Determinism: seed 42, deterministic=True, force_row_wise=True, fixed num_threads, sequential trials, TPE seeded.
"""
from __future__ import annotations

from typing import Callable, Optional

import lightgbm as lgb
import numpy as np
import pandas as pd

from .splits import SEED, group_kfold

NUM_THREADS = 8
BASE_PARAMS = {
    "seed": SEED, "bagging_seed": SEED, "feature_fraction_seed": SEED, "data_random_seed": SEED,
    "deterministic": True, "force_row_wise": True, "num_threads": NUM_THREADS, "verbosity": -1,
    "max_bin": 255, "cat_smooth": 10, "min_data_per_group": 50,
}

FoldTransform = Callable[[pd.DataFrame, np.ndarray, pd.DataFrame], tuple[pd.DataFrame, pd.DataFrame]]


def default_space(trial) -> dict:
    """Plan M2 search space."""
    return {
        "num_leaves": trial.suggest_int("num_leaves", 15, 255, log=True),
        "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.1, log=True),
        "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 20, 300, log=True),
        "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
        "bagging_fraction": trial.suggest_float("bagging_fraction", 0.6, 1.0),
        "bagging_freq": 1,
        "lambda_l2": trial.suggest_float("lambda_l2", 0.0, 10.0),
    }


def _dataset(X, y, w=None, ref=None):
    return lgb.Dataset(X, label=y, weight=w, reference=ref, free_raw_data=False)


def cv_fit(params: dict, X: pd.DataFrame, y: np.ndarray, w: Optional[np.ndarray], groups: pd.Series, *,
           n_folds: int = 5, max_rounds: int = 3000, patience: int = 200,
           fold_transform: Optional[FoldTransform] = None, keep_models: bool = False,
           report: Optional[Callable[[int, float], None]] = None) -> dict:
    """Grouped K-fold with early stopping. Returns mean best score, best iterations, out-of-fold predictions."""
    scores, iters, models = [], [], []
    oof = np.full(len(y), np.nan)
    metric = params["metric"]
    for k, (tr, va) in enumerate(group_kfold(groups, n_folds)):
        Xtr, Xva = X.iloc[tr], X.iloc[va]
        if fold_transform is not None:
            Xtr, Xva = fold_transform(Xtr, y[tr], Xva)
        dtr = _dataset(Xtr, y[tr], None if w is None else w[tr])
        dva = _dataset(Xva, y[va], None if w is None else w[va], ref=dtr)
        b = lgb.train(params, dtr, num_boost_round=max_rounds, valid_sets=[dva], valid_names=["valid"],
                      callbacks=[lgb.early_stopping(patience, verbose=False)])
        scores.append(float(b.best_score["valid"][metric]))
        iters.append(int(b.best_iteration))
        oof[va] = b.predict(Xva, num_iteration=b.best_iteration)
        if keep_models:
            models.append(b)
        if report is not None:
            report(k, float(np.mean(scores)))
    return {"score": float(np.mean(scores)), "fold_scores": scores, "best_iters": iters, "oof": oof, "models": models}


def tune(X: pd.DataFrame, y: np.ndarray, w: Optional[np.ndarray], groups: pd.Series, base: dict, *,
         n_trials: int, space: Callable = default_space, n_folds: int = 5, max_rounds: int = 3000,
         patience: int = 200, fold_transform: Optional[FoldTransform] = None, direction: str = "minimize") -> dict:
    """Optuna TPE (seed 42, sequential) over `space`; objective = mean grouped-CV early-stopped metric."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=SEED)
    pruner = optuna.pruners.MedianPruner(n_startup_trials=8, n_warmup_steps=1)
    study = optuna.create_study(direction=direction, sampler=sampler, pruner=pruner)

    def objective(trial):
        params = {**BASE_PARAMS, **base, **space(trial)}

        def report(step, value):
            trial.report(value, step)
            if trial.should_prune():
                raise optuna.TrialPruned()

        r = cv_fit(params, X, y, w, groups, n_folds=n_folds, max_rounds=max_rounds, patience=patience,
                   fold_transform=fold_transform, report=report)
        trial.set_user_attr("best_iters", r["best_iters"])
        return r["score"]

    def progress(st, t):   # one flushed line per trial, so a redirected log shows progress
        best = st.best_value if any(x.state.name == "COMPLETE" for x in st.trials) else float("nan")
        print(f"  trial {t.number + 1}/{n_trials} {t.state.name.lower()} value {t.value} best {best:.4f}", flush=True)

    study.optimize(objective, n_trials=n_trials, show_progress_bar=False, callbacks=[progress])
    best = study.best_trial
    params = {**BASE_PARAMS, **base, **default_space_fixed(best.params)}
    n_rounds = max(1, int(round(np.mean(best.user_attrs["best_iters"]) * 1.1)))
    return {"params": params, "n_rounds": n_rounds, "cv_score": float(best.value),
            "best_iters": best.user_attrs["best_iters"], "n_trials": len(study.trials),
            "n_complete": sum(t.state.name == "COMPLETE" for t in study.trials)}


def default_space_fixed(p: dict) -> dict:
    out = dict(p)
    if "bagging_fraction" in out:
        out["bagging_freq"] = 1
    return out


def refit(params: dict, X: pd.DataFrame, y: np.ndarray, w: Optional[np.ndarray], n_rounds: int) -> lgb.Booster:
    """Refit on all train rows with a fixed number of rounds (mean best iteration x 1.1)."""
    return lgb.train(params, _dataset(X, y, w), num_boost_round=n_rounds)
