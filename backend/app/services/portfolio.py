"""Bank portfolio view: Poor / Very poor homes ranked by improvement potential, plus summary statistics.

Improvement potential uses each home's confirmed package (all feasible, estimable measures). Homes are flagged by the
Green Home Score class, which uses energy per m2 and ratings, so a large home is never flagged for total use alone.
"""
from __future__ import annotations

import statistics
from functools import lru_cache
from typing import Optional

from ..data.loaders import homes_frame
from ..schemas.enums import FeasibilityState, ValueStatus
from ..schemas.property import home_from_row
from .baseline import get_baseline
from .carbon import carbon_change
from .feasibility import assess
from .packages import package_id
from .score import score_home
from .simulator import simulate

POOR = ("Poor", "Very poor")


@lru_cache(maxsize=4)
def _evaluate(split: Optional[str]) -> tuple:
    df = homes_frame()
    if split:
        df = df[df.split == split]
    classes: dict[str, int] = {}
    incomplete = 0
    rows = []
    for rec in df.to_dict("records"):
        h = home_from_row(rec)
        s = score_home(h)
        cls = s.classification or "unavailable"
        classes[cls] = classes.get(cls, 0) + 1
        if s.completeness != "7/7":
            incomplete += 1
        if cls not in POOR:
            continue
        b = get_baseline(h)
        feas = assess(h)
        ms = [f.measure for f in feas if f.state == FeasibilityState.feasible]
        sim = simulate(b, h, ms, feasibility=feas)
        ok = [r.measure for r in sim.measures if r.status == ValueStatus.ok]
        carb = carbon_change(sim) if sim.status == ValueStatus.ok else None
        rows.append({
            "home_id": h.home_id, "display_label": h.display_label, "postcode_outward": h.postcode_outward,
            "score": s.total, "classification": cls, "completeness": s.completeness, "missing_parts": s.missing_parts,
            "key_issues": s.key_issues, "package_id": package_id(ok),
            "improvement_potential_pct": sim.improvement_potential_pct,
            "improvement_potential_status": sim.improvement_potential_status.value,
            "improvement_potential_reason": sim.improvement_potential_reason,
            "gas_saving_kwh": sim.gas_saving_kwh, "elec_saving_kwh": sim.elec_saving_kwh,
            "carbon_saving_kg": carb.total_kg if carb else None,
            "floor_area_m2": h.floor_area_m2,
        })
    rows.sort(key=lambda r: (r["improvement_potential_pct"] is None, -(r["improvement_potential_pct"] or 0), r["home_id"]))
    return rows, classes, incomplete, len(df)


def portfolio(top_n: int = 50, split: Optional[str] = None) -> dict:
    rows, classes, incomplete, n = _evaluate(split)
    pots = [r["improvement_potential_pct"] for r in rows if r["improvement_potential_pct"] is not None]
    carbon = [r["carbon_saving_kg"] for r in rows if r["carbon_saving_kg"] is not None]
    summary = {
        "homes": n,
        "count_by_class": classes,
        "flagged_poor_or_very_poor": len(rows),
        "flagged_with_potential_available": len(pots),
        "flagged_potential_unavailable": len(rows) - len(pots),
        "median_improvement_potential_pct": statistics.median(pots) if pots else None,
        "total_carbon_saving_potential_t": sum(carbon) / 1000 if carbon else None,
        "share_incomplete_data_pct": 100 * incomplete / n if n else None,
        "notes": ["improvement potential = confirmed feasible package per home (estimates, benchmark baselines)",
                  "flags use the Green Home Score class (per-m2 intensity and ratings), not total consumption",
                  "carbon potential sums package savings; fabric combinations may be overestimated (D14)"],
    }
    return {"summary": summary, "homes": rows[:top_n]}
