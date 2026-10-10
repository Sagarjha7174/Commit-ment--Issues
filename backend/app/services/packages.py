"""Package search: every combination of feasible / needs_verification measures (<= 128, incl. do-nothing),
Pareto filter on (cost lower, carbon saving higher, purchased saving higher) and three featured picks.

Featured picks are chosen from confirmed (feasible-only), non-dominated packages with valid cost:
  lowest_cost_meeting_threshold  lowest cost among packages cutting >= threshold % of baseline emissions
  largest_carbon_saving          largest carbon saving
  best_carbon_per_pound          most kg CO2e saved per GBP among packages cutting >= threshold %
Ties: larger carbon saving, lower cost, fewer measures, package id. Fallbacks never lower the threshold silently.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Optional

from .. import config
from ..schemas.enums import FABRIC, FeasibilityState, MeasureId, ValueStatus, order_measures
from ..schemas.property import HomeRecord
from ..schemas.retrofit import FeasibilityItem, FeaturedPick, PackageResult, PackageSearch
from ..schemas.scenario import Assumptions, Baseline
from .carbon import carbon_change, emissions_kg
from .combination import calibrated_view
from .simulator import simulate

THRESHOLD_PCT = 10.0
COMBO_WARNING = ("combined fabric/controls savings may be overestimated: the simulator exceeds NEED combination "
                 "medians by 5.6-13.8 percentage points (docs/validation/simulator_vs_need.json, D14); "
                 "see the NEED-calibrated reference figures (D17)")
LABELS = {
    "lowest_cost_meeting_threshold": "Lowest-cost package cutting emissions by at least {t:g}%",
    "largest_carbon_saving": "Largest carbon saving",
    "best_carbon_per_pound": "Most carbon saved per pound among packages cutting at least {t:g}%",
}


def package_id(measures) -> str:
    ids = sorted(m.value if isinstance(m, MeasureId) else m for m in measures)
    return "+".join(ids) if ids else "none"


# ---------------- pure selection logic (tested on hand-built cases) ----------------

@dataclass
class Cand:
    package_id: str
    cost: Optional[float]
    carbon: float
    purchased: float
    n_measures: int
    confirmed: bool = True
    carbon_pct: float = 0.0
    must_verify: list = field(default_factory=list)


def _key(c: Cand):
    return (-c.carbon, c.cost if c.cost is not None else float("inf"), c.n_measures, c.package_id)


def pareto(cands: list[Cand]) -> dict[str, Optional[str]]:
    """package_id -> id of a dominating package (None if non-dominated). Packages without cost are not compared."""
    out: dict[str, Optional[str]] = {}
    costed = [c for c in cands if c.cost is not None]
    for p in cands:
        out[p.package_id] = None
        if p.cost is None:
            continue
        for q in sorted(costed, key=_key):
            if q is p:
                continue
            if (q.cost <= p.cost and q.carbon >= p.carbon and q.purchased >= p.purchased
                    and (q.cost < p.cost or q.carbon > p.carbon or q.purchased > p.purchased)):
                out[p.package_id] = q.package_id
                break
    return out


def select_featured(cands: list[Cand], threshold_pct: float = THRESHOLD_PCT, budget: Optional[float] = None):
    """Return (featured picks, fallback messages)."""
    t = threshold_pct
    # featured picks compare confirmed packages with each other (a conditional package cannot displace a confirmed one)
    dom = pareto([c for c in cands if c.confirmed])
    within = [c for c in cands if budget is None or c.cost is None or c.cost <= budget]
    confirmed = [c for c in within if c.confirmed and c.package_id != "none"]
    fallbacks: list[str] = []
    picks: list[FeaturedPick] = []

    def pick(obj, cid=None, msg=None, alts=()):
        picks.append(FeaturedPick(objective=obj, label=LABELS[obj].format(t=t), package_id=cid, message=msg,
                                  alternatives=list(alts)))

    if not confirmed:
        conditional = sorted([c for c in within if c.package_id != "none"], key=_key)
        if conditional:
            verify = sorted({v for c in conditional for v in c.must_verify})
            msg = "only conditional packages: verify " + "; ".join(verify) + " before choosing"
        else:
            msg = "no package can be estimated for this home"
        fallbacks.append(msg)
        for obj in LABELS:
            pick(obj, None, msg, [c.package_id for c in conditional[:3]])
        return picks, fallbacks

    if max(c.carbon for c in confirmed) <= 0:
        msg = "no package cuts emissions; trade-offs shown (purchased-energy change vs carbon)"
        fallbacks.append(msg)
        alts = [c.package_id for c in sorted(confirmed, key=lambda c: (-c.purchased, c.package_id))[:3]]
        for obj in LABELS:
            pick(obj, None, msg, alts)
        return picks, fallbacks

    nd = [c for c in confirmed if dom.get(c.package_id) is None]
    costed = [c for c in nd if c.cost is not None]
    largest = sorted(nd, key=_key)[0]
    if not costed:
        msg = "no valid cost data: carbon options shown without cost rankings"
        fallbacks.append(msg)
        pick("lowest_cost_meeting_threshold", None, msg)
        pick("largest_carbon_saving", largest.package_id)
        pick("best_carbon_per_pound", None, msg)
        return picks, fallbacks

    meets = [c for c in costed if c.carbon_pct >= t]
    pick("largest_carbon_saving", largest.package_id)
    if not meets:
        msg = f"no package meets the selection threshold ({t:g}% of baseline emissions)"
        fallbacks.append(msg)
        alts = [c.package_id for c in sorted([c for c in nd if c.carbon > 0], key=_key)[:3]]
        pick("lowest_cost_meeting_threshold", None, msg, alts)
        pick("best_carbon_per_pound", None, msg, alts)
    else:
        cheapest = sorted(meets, key=lambda c: (c.cost, -c.carbon, c.n_measures, c.package_id))[0]
        per_pound = [c for c in meets if c.cost and c.cost > 0]
        pick("lowest_cost_meeting_threshold", cheapest.package_id)
        if per_pound:
            best = sorted(per_pound, key=lambda c: (-(c.carbon / c.cost), -c.carbon, c.cost, c.n_measures, c.package_id))[0]
            pick("best_carbon_per_pound", best.package_id)
        else:
            pick("best_carbon_per_pound", None, "no package with a positive cost meets the threshold")
    picks.sort(key=lambda p: list(LABELS).index(p.objective))
    return picks, fallbacks


# ---------------- search over a real home ----------------

def _cost(measures: list[MeasureId]) -> tuple[Optional[float], str]:
    total, notes = 0.0, []
    for m in measures:
        c = config.measure_spec(m.value)["cost"]
        if c.get("mid") is None or c.get("status") == "unavailable":
            return None, f"cost unavailable for {m.value}"
        total += float(c["mid"])
        if c.get("status") != "derived_from_data":
            notes.append(f"{m.value}: {c.get('status')}")
    prov = "assumption: catalogue mid (EPC indicative cost, York 2022-26)"
    return total, prov + ("; " + "; ".join(notes) if notes else "")


def candidate_measures(home: HomeRecord, baseline: Baseline, feas: list[FeasibilityItem], a: Assumptions):
    """Feasible / needs_verification measures whose impact can be estimated alone; the rest excluded with a reason."""
    keep, excluded = [], {}
    for f in feas:
        if f.state == FeasibilityState.infeasible:
            excluded[f.measure.value] = f"infeasible: {f.reason_code}"
            continue
        s = simulate(baseline, home, [f.measure], a, feas)
        row = s.measures[0]
        if s.status != ValueStatus.ok or row.status != ValueStatus.ok:
            excluded[f.measure.value] = f"not estimated: {row.reason_code or s.reason_code}"
            continue
        keep.append(f.measure)
    return keep, excluded


def search(home: HomeRecord, baseline: Baseline, feas: list[FeasibilityItem], assumptions: Optional[Assumptions] = None,
           threshold_pct: float = THRESHOLD_PCT, budget: Optional[float] = None,
           include_calibrated: bool = True) -> PackageSearch:
    a = assumptions or Assumptions()
    fmap = {f.measure: f for f in feas}
    keep, excluded = candidate_measures(home, baseline, feas, a)
    base_kg = None
    if baseline.gas_kwh is not None and baseline.elec_kwh is not None:
        base_kg = emissions_kg(baseline.gas_kwh * a.baseline_scale, baseline.elec_kwh * a.baseline_scale)
    validated = {m["id"]: m["validated"] for m in config.catalogue()["measures"]}

    results: list[PackageResult] = []
    cands: list[Cand] = []
    for r in range(len(keep) + 1):
        for combo in itertools.combinations(keep, r):
            ms = order_measures(combo)
            pid = package_id(ms)
            sim = simulate(baseline, home, ms, a, feas)
            carb = carbon_change(sim)
            verify = [f"{m.value} ({', '.join(fmap[m].missing_inputs) or fmap[m].reason_code})"
                      for m in ms if fmap[m].state == FeasibilityState.needs_verification]
            cost, cost_prov = _cost(ms)
            warns = []
            if sum(1 for m in ms if m in FABRIC or m in (MeasureId.double_glazing, MeasureId.smart_thermostat)) >= 2:
                warns.append(COMBO_WARNING)
            if sim.status != ValueStatus.ok:
                results.append(PackageResult(package_id=pid, measures=ms, confirmed=not verify, must_verify=verify,
                                             cost_gbp=cost, status=ValueStatus.unavailable, reason_code=sim.reason_code,
                                             eligible_for_cost_comparison=False))
                continue
            pr = PackageResult(
                package_id=pid, measures=ms, confirmed=not verify, must_verify=verify, cost_gbp=cost,
                cost_provenance=cost_prov, cost_status=ValueStatus.ok if cost is not None else ValueStatus.unavailable,
                eligible_for_cost_comparison=cost is not None,
                gas_saving_kwh=sim.gas_saving_kwh, elec_saving_kwh=sim.elec_saving_kwh,
                purchased_saving_kwh=sim.purchased_saving_kwh, improvement_potential_pct=sim.improvement_potential_pct,
                carbon_saving_kg=carb.total_kg, carbon_saving_pct=carb.saving_pct_of_baseline,
                carbon_per_pound_kg=(carb.total_kg / cost) if cost else None,
                unvalidated_impacts=[m.value for m in ms if not validated[m.value]], warnings=warns,
                calibrated=calibrated_view(baseline, home, ms, a, feas) if (warns and include_calibrated) else None)
            results.append(pr)
            cands.append(Cand(pid, cost, carb.total_kg, sim.purchased_saving_kwh, len(ms), not verify,
                              carb.saving_pct_of_baseline or 0.0, verify))

    # dominance shown per row: confirmed packages vs confirmed packages; conditional packages vs all packages
    dom = {**pareto(cands), **pareto([c for c in cands if c.confirmed])}
    for pr in results:
        pr.dominated_by = dom.get(pr.package_id)
        pr.dominated = pr.dominated_by is not None
    featured, fallbacks = select_featured(cands, threshold_pct, budget) if cands else (
        [FeaturedPick(objective=o, label=LABELS[o].format(t=threshold_pct), message="baseline unavailable: no packages estimated")
         for o in LABELS], ["baseline unavailable: no packages estimated"])
    results.sort(key=lambda p: (p.status != ValueStatus.ok, -(p.carbon_saving_kg or 0), p.cost_gbp or 0, len(p.measures), p.package_id))
    return PackageSearch(packages=results, featured=featured, fallbacks=fallbacks, excluded_measures=excluded,
                         threshold_pct=threshold_pct, budget_gbp=budget, baseline_emissions_kg=base_kg)
