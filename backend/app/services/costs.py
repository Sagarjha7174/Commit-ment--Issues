"""Measure costs for one home (DECISIONS D8, D23).

Base cost = catalogue mid (York EPC indicative-cost text). Two home-specific adjustments:
- partial glazing: only the single-glazed share is replaced (multi_glaze_pct missing -> 50%);
- size: x (floor area / York reference floor area)^gamma per measure, clamped, once the reference area is calibrated
  (configs/engine_calibration.json); gamma values are assumptions (configs/engine_params.json "costs").
"""
from __future__ import annotations

from typing import Optional

from .. import config
from ..schemas.enums import MeasureId
from ..schemas.property import HomeRecord


def _params() -> dict:
    return config.engine_params().get("costs", {})


def size_factor(measure: MeasureId, home: Optional[HomeRecord]) -> tuple[float, Optional[str]]:
    cal = config.engine_calibration() or {}
    ref = cal.get("reference_floor_area_m2")
    gamma = _params().get("size_exponent", {}).get(measure.value, 0.0)
    if home is None or ref is None or not gamma or home.floor_area_m2 is None or home.flag_floor_area_implausible:
        return 1.0, None
    lo, hi = _params().get("size_factor_clamp", [0.5, 2.0])
    f = min(max((home.floor_area_m2 / ref) ** gamma, lo), hi)
    return f, f"size x{f:.2f} ({home.floor_area_m2:g} m² vs York reference {ref:g} m², exponent {gamma:g})"


def measure_cost(measure: MeasureId, home: Optional[HomeRecord] = None) -> tuple[Optional[float], list[str]]:
    """(gross cost in GBP or None, notes)."""
    c = config.measure_spec(measure.value)["cost"]
    if c.get("mid") is None or c.get("status") == "unavailable":
        return None, [f"cost unavailable for {measure.value}"]
    cost, notes = float(c["mid"]), []
    if c.get("status") != "derived_from_data":
        notes.append(f"{measure.value}: {c.get('status')}")
    if measure == MeasureId.double_glazing and home is not None and home.glazing == "partial":
        share = 1 - (home.multi_glaze_pct if home.multi_glaze_pct is not None else 50.0) / 100
        cost *= share
        notes.append(f"double_glazing: only the single-glazed {share:.0%} of windows replaced (D23)")
    f, note = size_factor(measure, home)
    if note:
        cost *= f
        notes.append(f"{measure.value}: {note}")
    return cost, notes


def package_cost(measures: list[MeasureId], home: Optional[HomeRecord] = None) -> tuple[Optional[float], str]:
    total, notes = 0.0, []
    for m in measures:
        c, n = measure_cost(m, home)
        if c is None:
            return None, n[0]
        total += c
        notes += n
    prov = "assumption: catalogue mid (EPC indicative cost, York 2022-26)"
    return total, prov + ("; " + "; ".join(notes) if notes else "")
