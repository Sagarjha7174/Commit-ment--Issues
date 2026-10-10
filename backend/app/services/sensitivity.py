"""Limited one-at-a-time sensitivity of the featured package picks. NOT a confidence interval."""
from __future__ import annotations

from typing import Optional

from .. import config
from ..schemas.enums import CombinationMode, ImpactLevel
from ..schemas.property import HomeRecord
from ..schemas.retrofit import FeasibilityItem, PackageSearch
from ..schemas.scenario import Assumptions, Baseline
from .packages import search

LABEL = "limited sensitivity analysis: one assumption changed at a time; not a confidence interval"
UNTESTED = ["roof orientation and shading (PV yield)", "occupancy and behaviour (incl. rebound)", "weather / degree-days",
            "ventilation and infiltration", "installation quality", "energy prices and tariffs", "heat-pump sizing and flow temperature"]


def variants(base: Assumptions) -> list[tuple[str, str, Assumptions]]:
    g = config.catalogue_globals()
    other = g["other_gas_share"]
    scop = g["heat_pump_scop"]
    v = [
        ("baseline_minus_15pct", "baseline energy x 0.85", {"baseline_scale": base.baseline_scale * 0.85}),
        ("baseline_plus_15pct", "baseline energy x 1.15", {"baseline_scale": base.baseline_scale * 1.15}),
        ("scop_low", f"heat pump SCOP {scop['low']}", {"heat_pump_scop": scop["low"]}),
        ("scop_high", f"heat pump SCOP {scop['high']}", {"heat_pump_scop": scop["high"]}),
        ("gas_split_65_35", "space/water gas split 0.65/0.35", {"space_share_of_heat_water_gas": 0.65}),
        ("gas_split_85_15", "space/water gas split 0.85/0.15", {"space_share_of_heat_water_gas": 0.85}),
        ("other_gas_low", f"cooking gas share {other / 2:.4f} (half ECUK)", {"other_gas_share": other / 2}),
        ("other_gas_high", f"cooking gas share {other * 2:.4f} (double ECUK)", {"other_gas_share": other * 2}),
        ("impacts_low", "measure impacts at catalogue low", {"impact_level": ImpactLevel.low}),
        ("impacts_high", "measure impacts at catalogue high", {"impact_level": ImpactLevel.high}),
        ("headline_impacts", "national headline impacts instead of segment-adjusted (D15)", {"segment_impacts": False}),
        ("need_calibrated_combinations", "fabric/controls combinations scaled to NEED medians (D17)",
         {"combination_mode": CombinationMode.need_calibrated}),
    ]
    return [(n, d, base.model_copy(update=u)) for n, d, u in v]


def run(home: HomeRecord, baseline: Baseline, feas: list[FeasibilityItem], base_search: PackageSearch,
        assumptions: Optional[Assumptions] = None, threshold_pct: Optional[float] = None,
        budget: Optional[float] = None) -> dict:
    a = assumptions or Assumptions()
    t = base_search.threshold_pct if threshold_pct is None else threshold_pct
    base = {f.objective: f.package_id for f in base_search.featured}
    runs = []
    for name, desc, va in variants(a):
        ps = search(home, baseline, feas, va, t, budget, include_calibrated=False)  # only the picks matter here
        picks = {f.objective: f.package_id for f in ps.featured}
        runs.append({"name": name, "change": desc, "featured": picks,
                     "changed_objectives": sorted(o for o in base if picks.get(o) != base[o])})
    survival = {}
    for obj, pid in base.items():
        changed = [r["name"] for r in runs if obj in r["changed_objectives"]]
        survival[obj] = {"base_pick": pid, "survives": f"{len(runs) - len(changed)}/{len(runs)}", "changed_under": changed}
    # annotate featured packages
    by_id = {p.package_id: p for p in base_search.packages}
    for obj, pid in base.items():
        if pid in by_id:
            by_id[pid].sensitivity = {**(by_id[pid].sensitivity or {}), obj: survival[obj]}
    return {"label": LABEL, "runs": runs, "survival": survival, "untested": UNTESTED}
