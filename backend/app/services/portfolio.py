"""Bank portfolio view: Poor / Very poor homes ranked by improvement potential, plus summary statistics.

Improvement potential uses each home's confirmed package (all feasible, estimable measures). Homes are flagged by the
Green Home Score class, which uses energy per m2 and ratings, so a large home is never flagged for total use alone.

Because a heat pump alone gives ~60% purchased-energy reduction in a gas home, each row also shows the fabric/controls
-only potential, the net cost after grants, the bill change and kg CO2e per GBP, and the list can be ranked by
improvement_potential (the brief's default), fabric_potential, carbon_per_pound or carbon_saving (D29).
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
from .money import bill_change, finance_summary
from .simulator import FABRIC_CONTROLS, simulate

POOR = ("Poor", "Very poor")
RANK_KEYS = {
    "improvement_potential": "improvement_potential_pct",
    "fabric_potential": "fabric_improvement_potential_pct",
    "carbon_per_pound": "carbon_per_pound_kg",
    "carbon_saving": "carbon_saving_kg",
}


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
        fabric = [m for m in ms if m in FABRIC_CONTROLS]
        sim_f = simulate(b, h, fabric, feasibility=feas) if fabric else None
        carb_f = carbon_change(sim_f) if sim_f is not None and sim_f.status == ValueStatus.ok else None
        bill = bill_change(sim)
        fin = finance_summary(ok, h, bill) if ok and sim.status == ValueStatus.ok else {}
        net = fin.get("net_cost_gbp")
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
            "heat_pump_in_package": any(m.value == "heat_pump" for m in ok),
            "fabric_improvement_potential_pct": sim_f.improvement_potential_pct if sim_f is not None else None,
            "fabric_carbon_saving_kg": carb_f.total_kg if carb_f else None,
            "gross_cost_gbp": fin.get("gross_cost_gbp"), "grants_gbp": fin.get("grants_gbp"), "net_cost_gbp": net,
            "bill_saving_gbp": bill.get("saving_gbp"), "payback_years": fin.get("payback_years"),
            "carbon_per_pound_kg": (carb.total_kg / net) if (carb and net) else None,
        })
    rows.sort(key=lambda r: (r["improvement_potential_pct"] is None, -(r["improvement_potential_pct"] or 0), r["home_id"]))
    return rows, classes, incomplete, len(df)


def rank(rows: list[dict], rank_by: str = "improvement_potential") -> list[dict]:
    """Descending by the chosen metric; unavailable values ranked last (never treated as 0); ties by home_id."""
    if rank_by not in RANK_KEYS:
        raise ValueError(f"rank_by must be one of {sorted(RANK_KEYS)}")
    k = RANK_KEYS[rank_by]
    return sorted(rows, key=lambda r: (r[k] is None, -(r[k] or 0), r["home_id"]))


def portfolio(top_n: int = 50, split: Optional[str] = None, rank_by: str = "improvement_potential") -> dict:
    rows, classes, incomplete, n = _evaluate(split)
    rows = rank(rows, rank_by)
    fab = [r["fabric_improvement_potential_pct"] for r in rows if r["fabric_improvement_potential_pct"] is not None]
    fab_carbon = [r["fabric_carbon_saving_kg"] for r in rows if r["fabric_carbon_saving_kg"] is not None]
    nets = [r["net_cost_gbp"] for r in rows if r["net_cost_gbp"] is not None]
    bills = [r["bill_saving_gbp"] for r in rows if r["bill_saving_gbp"] is not None]
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
        "rank_by": rank_by,
        "median_fabric_improvement_potential_pct": statistics.median(fab) if fab else None,
        "total_fabric_carbon_saving_potential_t": sum(fab_carbon) / 1000 if fab_carbon else None,
        "total_net_cost_gbp": sum(nets) if nets else None,
        "homes_with_bill_falling": sum(1 for x in bills if x > 0),
        "notes": ["improvement potential = confirmed feasible package per home (estimates, benchmark baselines)",
                  "flags use the Green Home Score class (per-m2 intensity and ratings), not total consumption",
                  "carbon potential sums package savings; fabric combinations may be overestimated (D14)",
                  "heat pumps dominate purchased-energy potential; fabric_improvement_potential_pct shows insulation and controls alone",
                  "costs net of Boiler Upgrade Scheme grants, subject to eligibility (D27)"],
    }
    return {"summary": summary, "homes": rows[:top_n]}
