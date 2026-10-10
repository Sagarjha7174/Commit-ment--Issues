"""Home-specific NEED impacts (DECISIONS D15).

The catalogue's headline impact is a national median. NEED also publishes the same measure by EPC band, property age,
property type and region (`impact_by_segment`). Segment medians are noisy (loft IQR is about -16% to +22%), so each
segment's deviation from the headline is shrunk toward zero by empirical Bayes:

    se(segment median) = 1.2533 * (IQR / 1.349) / sqrt(n)
    tau^2 (per measure x dimension) = max(0, var(segment deviations) - mean(se^2))
    w = tau^2 / (tau^2 + se^2);  shrunk deviation = w * (segment median - headline median)

The home's shrunk deviations (one per dimension it belongs to) are added to every impact level, assuming the
dimensions act independently, and the result is floored at 0 (an expected saving is never an increase).
Dimensions the home cannot be placed in (e.g. flats for property type, missing EPC band) contribute nothing.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import Optional

from .. import config
from ..schemas.property import HomeRecord

DIMENSIONS = ("epc_rating", "property_age", "property_type", "region")
HEADLINE = "All domestic properties"


def _params() -> dict:
    return config.engine_params()["segment_impacts"]


def age_segment(age_band: Optional[str]) -> Optional[str]:
    if not age_band:
        return None
    s = age_band.strip().lower()
    if s.startswith("before"):
        return "Pre 1919"
    years = [int(y) for y in re.findall(r"\d{4}", s)]
    if not years:
        return None
    mid = (years[0] + years[-1]) / 2
    for upper, label in _params()["age_segments"]:
        if mid <= upper:
            return label
    return None


def type_segment(property_type: Optional[str], built_form: Optional[str]) -> Optional[str]:
    if property_type == "Bungalow":
        return "Bungalow"
    if property_type == "House" and built_form:
        return _params()["type_segment"].get(built_form)
    return None   # flats, maisonettes, park homes: NEED reports no segment


def segments_for(home: HomeRecord) -> dict[str, Optional[str]]:
    p = _params()
    return {
        "epc_rating": p["epc_rating_segment"].get(home.rating or ""),
        "property_age": age_segment(home.age_band),
        "property_type": type_segment(home.property_type, home.built_form),
        "region": p["region_label"],
    }


def _se(seg: dict) -> Optional[float]:
    n, q1, q3 = seg.get("n"), seg.get("q1"), seg.get("q3")
    if not n or q1 is None or q3 is None or n <= 0:
        return None
    return 1.2533 * ((q3 - q1) / 1.349) / math.sqrt(n)


@lru_cache(maxsize=None)
def shrinkage(measure_id: str) -> dict[str, dict[str, dict]]:
    """dimension -> segment -> {deviation, se, weight, shrunk, n}; empty when the measure has no segment tables."""
    spec = config.measure_spec(measure_id)
    by = spec.get("impact_by_segment") or {}
    out: dict[str, dict[str, dict]] = {}
    for dim in DIMENSIONS:
        segs = (by.get(dim) or {}).get("segments", {})
        head = segs.get(HEADLINE, {}).get("median_pct")
        if head is None:
            continue
        rows = {}
        for name, seg in segs.items():
            if name == HEADLINE or seg.get("status") != "observed" or seg.get("median_pct") is None:
                continue
            se = _se(seg)
            if se is None:
                continue
            rows[name] = {"deviation": seg["median_pct"] - head, "se": se, "n": seg["n"]}
        if len(rows) >= 2:
            devs = [r["deviation"] for r in rows.values()]
            mean = sum(devs) / len(devs)
            var = sum((d - mean) ** 2 for d in devs) / (len(devs) - 1)
            tau2 = max(0.0, var - sum(r["se"] ** 2 for r in rows.values()) / len(rows))
        else:
            tau2 = 0.0
        for r in rows.values():
            r["tau2"] = tau2
            r["weight"] = tau2 / (tau2 + r["se"] ** 2) if tau2 > 0 else 0.0
            r["shrunk"] = r["weight"] * r["deviation"]
        out[dim] = rows
    return out


def adjustment(measure_id: str, home: HomeRecord) -> tuple[float, dict]:
    """Total shrunk deviation for this home and the per-dimension detail (segment, deviation, weight, shrunk)."""
    table = shrinkage(measure_id)
    total, detail = 0.0, {}
    for dim, seg in segments_for(home).items():
        row = table.get(dim, {}).get(seg) if seg else None
        if row is None:
            detail[dim] = {"segment": seg, "used": False}
            continue
        total += row["shrunk"]
        detail[dim] = {"segment": seg, "used": True, "deviation": round(row["deviation"], 6),
                       "weight": round(row["weight"], 4), "shrunk": round(row["shrunk"], 6)}
    return total, detail


def impact(measure_id: str, level: str, home: Optional[HomeRecord], enabled: bool = True) -> tuple[float, Optional[dict]]:
    """Impact fraction for this home at the given level, plus the segment detail (None when not adjusted)."""
    base = float(config.measure_spec(measure_id)["impact"][level])
    if not enabled or home is None or not shrinkage(measure_id):
        return base, None
    adj, detail = adjustment(measure_id, home)
    value = base + adj
    if _params()["floor_at_zero"]:
        value = max(value, 0.0)
    return value, {"headline": base, "adjustment": round(adj, 6), "segments": detail}
