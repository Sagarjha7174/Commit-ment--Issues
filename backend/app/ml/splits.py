"""Splits: the existing hashed home split (never re-split) and deterministic group folds inside train."""
from __future__ import annotations

import hashlib
from typing import Iterator

import numpy as np
import pandas as pd

SEED = 42


def group_fold(groups: pd.Series, n_folds: int = 5, seed: int = SEED) -> np.ndarray:
    """Fold id per row from a hash of (seed, group): every row of a group lands in the same fold; reproducible."""
    def h(g) -> int:
        return int(hashlib.sha1(f"{seed}:{g}".encode()).hexdigest()[:8], 16) % n_folds
    codes = {g: h(g) for g in pd.unique(groups.astype(str))}
    return groups.astype(str).map(codes).to_numpy()


def group_kfold(groups: pd.Series, n_folds: int = 5, seed: int = SEED) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """(train_idx, valid_idx) positional indices, grouped (GroupKFold semantics, hash-assigned)."""
    f = group_fold(groups, n_folds, seed)
    for k in range(n_folds):
        yield np.flatnonzero(f != k), np.flatnonzero(f == k)


def attach_home_split(df: pd.DataFrame, homes: pd.DataFrame, key: str = "property_id") -> pd.DataFrame:
    """Rows inherit their home's split from homes_tagged (certificates have no split column)."""
    if "split" in df.columns:
        df = df.drop(columns="split")
    return df.merge(homes[[key, "split"]], on=key, how="left")
