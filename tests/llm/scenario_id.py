"""Full-state scenario IDs (plan_final.md decision 13 and the contract rules).

The ID is the SHA-256 of a canonical JSON of everything that affects a
calculation: property inputs and their provenance, baseline values, selected
measures (in catalogue order), catalogue / model / emissions-factor / score-
mapping versions, assumptions and overrides. Same state gives the same ID; any
calculation-affecting change gives a new one. The data timestamp is excluded
because it does not change any number.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

FLOAT_DECIMALS = 6
EXCLUDED_KEYS = frozenset({"data_timestamp", "scenario_id"})


def _canonical(obj: Any, decimals: int) -> Any:
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise ValueError("NaN/inf cannot be part of a scenario state; use None plus a status")
        r = round(obj, decimals)
        return 0.0 if r == 0 else r  # -0.0 and 0.0 hash the same
    if isinstance(obj, dict):
        return {str(k): _canonical(v, decimals) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))
                if str(k) not in EXCLUDED_KEYS}
    if isinstance(obj, (list, tuple)):
        return [_canonical(v, decimals) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(_canonical(v, decimals) for v in obj)
    if hasattr(obj, "model_dump"):
        return _canonical(obj.model_dump(mode="json"), decimals)
    raise TypeError(f"cannot canonicalise {type(obj).__name__}")


def canonical_json(state: Any, decimals: int = FLOAT_DECIMALS) -> str:
    """Sorted keys, fixed float rounding, no whitespace. Lists keep their order:
    callers must put measures in catalogue order (measures.ordered) first."""
    return json.dumps(_canonical(state, decimals), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def scenario_id(state: Any, decimals: int = FLOAT_DECIMALS) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(state, decimals).encode("utf-8")).hexdigest()
