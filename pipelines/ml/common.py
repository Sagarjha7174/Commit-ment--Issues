"""Shared paths and loaders for the ML pipelines. Every parquet read goes through the privacy guard."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import config  # noqa: E402
from backend.app.ml.privacy import safe_read_parquet  # noqa: E402

PROC = ROOT / "data" / "processed"
YORK = config.REGION_DIR
VALIDATION = ROOT / "docs" / "validation"
CERT_FEATURES = YORK / "ml_cert_features.parquet"
EPC_PAIRS = YORK / "ml_epc_pairs.parquet"


def homes(columns: list[str]) -> pd.DataFrame:
    return safe_read_parquet(config.HOMES_TAGGED, columns=columns)


def cert_features() -> pd.DataFrame:
    if not CERT_FEATURES.exists():
        raise SystemExit("run pipelines/ml/build_feature_tables.py first (make ml-data)")
    return pd.read_parquet(CERT_FEATURES)


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=False, default=_default) + "\n")


def _default(o):
    import numpy as np
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def rnd(x, k: int = 4):
    """Round for reporting (None stays None)."""
    if x is None:
        return None
    try:
        return round(float(x), k)
    except (TypeError, ValueError):
        return x
