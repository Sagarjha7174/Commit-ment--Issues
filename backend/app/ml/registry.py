"""Model registry: models/<name>/model.txt (LightGBM text) + meta.json, and configs/model_registry.json.

Only models listed as shipped (they beat their baseline on validation) are loaded. Loading is lazy (lru_cache) and
returns None when a model is absent, so every service abstains with a reason instead of failing.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

from .. import config

MODELS_DIR: Path = config.ROOT / "models"
REGISTRY_FILE: Path = config.CONFIGS / "model_registry.json"


@dataclass(frozen=True)
class LoadedModel:
    name: str
    booster: object
    meta: dict

    @property
    def version(self) -> str:
        return self.meta["version"]

    def frame(self, rows: list[dict] | pd.DataFrame) -> pd.DataFrame:
        from .features import to_frame
        return to_frame(rows, self.meta["features"], self.meta.get("categories", {}))

    def predict(self, rows: list[dict] | pd.DataFrame):
        return self.booster.predict(self.frame(rows))

    def contributions(self, rows: list[dict] | pd.DataFrame):
        """TreeSHAP contributions per feature (LightGBM pred_contrib); the last column is the expected value."""
        return self.booster.predict(self.frame(rows), pred_contrib=True)


def top_contributions(names: list[str], contrib, values: dict, k: int = 5) -> list[dict]:
    """The k features with the largest |contribution| (model output units), with the feature value used."""
    order = sorted(range(len(names)), key=lambda i: -abs(float(contrib[i])))[:k]
    out = []
    for i in order:
        v = values.get(names[i])
        out.append({"feature": names[i], "value": None if v is None or (isinstance(v, float) and v != v) else v,
                    "contribution": round(float(contrib[i]), 4)})
    return out


def read_registry() -> dict:
    return json.loads(REGISTRY_FILE.read_text()) if REGISTRY_FILE.exists() else {"version": "model-registry-v1", "models": {}}


def shipped_versions() -> dict[str, str]:
    """{name: version} of shipped models whose files are present; enters config.versions()."""
    out = {}
    for name, e in read_registry().get("models", {}).items():
        if e.get("shipped") and ((MODELS_DIR / name / "meta.json").exists() or (MODELS_DIR / f"{name}.json").exists()):
            out[name] = e["version"]
    return out


def is_shipped(name: str) -> bool:
    return name in shipped_versions()


@lru_cache(maxsize=None)
def get(name: str) -> Optional[LoadedModel]:
    """The shipped LightGBM model `name`, or None (absent / not shipped)."""
    if not is_shipped(name):
        return None
    d = MODELS_DIR / name
    if not (d / "model.txt").exists():
        return None
    import lightgbm as lgb
    meta = json.loads((d / "meta.json").read_text())
    return LoadedModel(name, lgb.Booster(model_file=str(d / "model.txt")), meta)


@lru_cache(maxsize=None)
def get_json(name: str) -> Optional[dict]:
    """A shipped non-GBM model stored as models/<name>.json (e.g. the hedonic value model), or None."""
    if not is_shipped(name):
        return None
    p = MODELS_DIR / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def clear() -> None:
    get.cache_clear()
    get_json.cache_clear()


def file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frame_hash(df: pd.DataFrame) -> str:
    """Hash of the training data (values and column names), recorded in meta.json."""
    h = hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes())
    h.update("|".join(map(str, df.columns)).encode())
    return h.hexdigest()[:16]


def save_booster(name: str, booster, meta: dict, models_dir: Optional[Path] = None) -> str:
    """Write model.txt + meta.json; the version is <name>-<sha256(model.txt)[:10]>."""
    d = (models_dir or MODELS_DIR) / name
    d.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(d / "model.txt"))
    version = f"{name}-{file_hash(d / 'model.txt')[:10]}"
    (d / "meta.json").write_text(json.dumps({**meta, "name": name, "version": version}, indent=1, default=str) + "\n")
    return version


def save_json_model(name: str, payload: dict, models_dir: Optional[Path] = None) -> str:
    d = models_dir or MODELS_DIR
    d.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, sort_keys=True, default=str)
    version = f"{name}-{hashlib.sha256(body.encode()).hexdigest()[:10]}"
    (d / f"{name}.json").write_text(json.dumps({**payload, "name": name, "version": version}, indent=1, default=str) + "\n")
    return version


def register(name: str, version: Optional[str], shipped: bool, gate: dict, headline: dict) -> None:
    """Record a model's gate result in configs/model_registry.json (shipped only if every gate passed)."""
    reg = read_registry()
    reg.setdefault("models", {})[name] = {"version": version, "shipped": bool(shipped), "gate": gate,
                                          "headline_val": headline}
    REGISTRY_FILE.write_text(json.dumps(reg, indent=1, sort_keys=True, default=str) + "\n")
    clear()
