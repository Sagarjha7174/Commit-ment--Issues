"""Decision audit generated from the computed scenario parts (never hand-written)."""
from __future__ import annotations

from typing import Optional

from ..schemas.enums import FeasibilityState, ValueStatus
from ..schemas.retrofit import FeasibilityItem, PackageSearch, SimResult
from ..schemas.scenario import Baseline

OBJECTIVE_TEXT = {
    "lowest_cost_meeting_threshold": "minimise cost subject to cutting baseline emissions by at least the threshold",
    "largest_carbon_saving": "maximise annual carbon saving",
    "best_carbon_per_pound": "maximise kg CO2e saved per GBP subject to the threshold",
}


def _pkg_summary(p) -> dict:
    return {"package_id": p.package_id, "cost_gbp": p.cost_gbp, "carbon_saving_kg": p.carbon_saving_kg,
            "carbon_saving_pct": p.carbon_saving_pct, "gas_saving_kwh": p.gas_saving_kwh,
            "elec_saving_kwh": p.elec_saving_kwh, "purchased_saving_kwh": p.purchased_saving_kwh,
            "grants_gbp": p.grants_gbp, "net_cost_gbp": p.net_cost_gbp, "bill_saving_gbp": p.bill_saving_gbp,
            "payback_years": p.payback_years}


def _difference(a, b) -> list[str]:
    sa, sb = {m.value for m in a.measures}, {m.value for m in b.measures}
    out = []
    if sa - sb:
        out.append("winner adds " + ", ".join(sorted(sa - sb)))
    if sb - sa:
        out.append("alternative adds " + ", ".join(sorted(sb - sa)))
    if a.cost_gbp is not None and b.cost_gbp is not None:
        out.append(f"cost difference {b.cost_gbp - a.cost_gbp:+,.0f} GBP (alternative minus winner)")
    if a.carbon_saving_kg is not None and b.carbon_saving_kg is not None:
        out.append(f"carbon difference {b.carbon_saving_kg - a.carbon_saving_kg:+,.0f} kg/yr")
    if a.bill_saving_gbp is not None and b.bill_saving_gbp is not None:
        out.append(f"annual bill saving difference {b.bill_saving_gbp - a.bill_saving_gbp:+,.0f} GBP (alternative minus winner)")
    if a.elec_saving_kwh is not None and b.elec_saving_kwh is not None and abs(b.elec_saving_kwh - a.elec_saving_kwh) > 1:
        out.append(f"electricity saving difference {b.elec_saving_kwh - a.elec_saving_kwh:+,.0f} kWh/yr (negative = more electricity used)")
    return out


def build_audit(scenario_id: str, versions: dict, baseline: Baseline, feas: list[FeasibilityItem], sim: SimResult,
                packages: Optional[PackageSearch], sensitivity: Optional[dict], warnings: list[str]) -> dict:
    audit = {
        "scenario_id": scenario_id,
        "versions": versions,
        "baseline": {"gas_kwh": baseline.gas_kwh, "elec_kwh": baseline.elec_kwh, "gas_provenance": baseline.gas_provenance.value,
                     "elec_provenance": baseline.elec_provenance.value, "source": baseline.source, "note": baseline.note,
                     "blocking_flags": baseline.blocking_flags, "gas_heated": baseline.gas_heated,
                     "elec_heated": baseline.elec_heated, "elec_heat_share": baseline.elec_heat_share,
                     "elec_heat_share_source": baseline.elec_heat_share_source},
        "assumptions_used": sim.assumptions,
        "feasibility": [{"measure": f.measure.value, "state": f.state.value, "reason": f.reason_code,
                         "missing_inputs": f.missing_inputs} for f in feas],
        "requested_package": {"status": sim.status.value,
                              "measures": [{"measure": r.measure.value, "status": r.status.value, "reason": r.reason_code}
                                           for r in sim.measures]},
    }
    unknowns = [f"{f.measure.value}: verify {', '.join(f.missing_inputs) or f.reason_code}"
                for f in feas if f.state == FeasibilityState.needs_verification]
    if baseline.source == "population_benchmark":
        unknowns.append("baseline is a NEED population benchmark, not this home's meter readings")
    if baseline.elec_heated:
        unknowns.append("electric heating share of electricity is a NEED benchmark difference, not metered (D16)")
    if any(r.measure.value == "heat_pump" and r.status == ValueStatus.ok for r in sim.measures):
        unknowns.append(f"existing boiler efficiency: {sim.assumptions.get('boiler_efficiency_source', 'assumption')}")
    if packages is not None:
        pk = packages.packages
        by_id = {p.package_id: p for p in pk}
        audit["packages_considered"] = {
            "count": len(pk),
            "excluded_measures": packages.excluded_measures,
            "dominated": {p.package_id: p.dominated_by for p in pk if p.dominated},
            "conditional": {p.package_id: p.must_verify for p in pk if not p.confirmed},
            "missing_cost": [p.package_id for p in pk if not p.eligible_for_cost_comparison],
            "threshold_pct": packages.threshold_pct,
            "budget_gbp": packages.budget_gbp,
        }
        audit["featured"] = [{"objective": f.objective, "objective_text": OBJECTIVE_TEXT[f.objective], "label": f.label,
                              "package": _pkg_summary(by_id[f.package_id]) if f.package_id in by_id else None,
                              "message": f.message, "alternatives": f.alternatives} for f in packages.featured]
        audit["fallbacks"] = packages.fallbacks
        picks = [f.package_id for f in packages.featured if f.package_id]
        if picks:
            winner = by_id[picks[0]]
            alt_id = next((p for p in picks[1:] if p != winner.package_id), None)
            alt = by_id[alt_id] if alt_id else None
            audit["winner"] = {"package": _pkg_summary(winner), "objective": packages.featured[[f.package_id for f in packages.featured].index(winner.package_id)].objective}
            audit["alternative"] = _pkg_summary(alt) if alt else None
            audit["main_factors"] = _difference(winner, alt) if alt else ["no distinct alternative among the featured picks"]
            unvalidated = sorted({m for p in (winner, alt) if p for m in p.unvalidated_impacts})
            if unvalidated:
                unknowns.append("impacts not validated against NEED: " + ", ".join(unvalidated))
            if any(p and p.warnings for p in (winner, alt)):
                unknowns.extend(sorted({w for p in (winner, alt) if p for w in p.warnings}))
    if sensitivity is not None:
        audit["sensitivity"] = {"label": sensitivity["label"], "survival": sensitivity["survival"],
                                "untested": sensitivity["untested"]}
    audit["unknowns"] = unknowns
    audit["warnings"] = warnings
    audit["improvement_potential"] = {"status": sim.improvement_potential_status.value,
                                      "pct": sim.improvement_potential_pct, "reason": sim.improvement_potential_reason}
    if sim.status != ValueStatus.ok:
        audit["requested_package"]["reason"] = sim.reason_code
    return audit
