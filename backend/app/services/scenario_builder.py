"""build(request) -> ScenarioResult: the ONLY writer of numbers for a scenario.

load home -> baseline -> feasibility -> simulate -> carbon -> score before/after -> packages -> sensitivity (optional)
-> valuation (gated) -> assemble with assumptions, warnings, versions and a deterministic scenario_id.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .. import config
from ..data.loaders import get_home
from ..schemas.enums import FABRIC, FeasibilityState, MeasureId, Provenance, ValueStatus, order_measures
from ..schemas.property import HomeRecord
from ..schemas.scenario import ScenarioRequest, ScenarioResult, Valuation, scenario_id
from . import audit as audit_mod
from . import packages as packages_mod
from . import sensitivity as sens_mod
from .baseline import get_baseline
from .carbon import carbon_change
from .feasibility import assess
from .score import score_after, score_home
from .simulator import simulate
from .units import resolve

PUBLIC_HOME_FIELDS = ("home_id", "display_label", "postcode_outward", "split", "rating", "sap_score", "property_type",
                      "built_form", "age_band", "floor_area_m2", "walls_rating", "roof_rating", "floor_rating", "glazing",
                      "multi_glaze_pct", "heating_type", "heating_rating", "controls", "solar_pv", "mains_gas",
                      "epc_age_years", "flag_stale_epc")


def public_home(home: HomeRecord) -> dict:
    d = home.model_dump(mode="json")
    out = {k: d[k] for k in PUBLIC_HOME_FIELDS}
    out["provenance"] = {k: v.value for k, v in home.provenance.items()}
    return out


def valuation() -> Valuation:
    g = config.value_gate()
    if g.get("status") == "enabled":
        return Valuation(status=ValueStatus.not_estimated, reason="value gate enabled but no value model is wired into the engine yet")
    return Valuation(status=ValueStatus.not_estimated,
                     reason=f"audit pending: property-value model gated off (value_gate status '{g.get('status')}', D10)")


def _energy_prov(b) -> Provenance:
    if b.source == "user_provided":
        return Provenance.user_provided
    if b.source == "mixed":
        return Provenance.derived
    return Provenance.population_benchmark


def build(request: ScenarioRequest, home: Optional[HomeRecord] = None) -> ScenarioResult:
    home = home or get_home(request.home_id)
    if home.home_id != request.home_id:
        raise ValueError("home does not match request.home_id")
    a = request.assumptions
    baseline = get_baseline(home, request.user_reading)
    feas = assess(home)
    fmap = {f.measure: f for f in feas}

    requested = order_measures(request.measures) if request.measures is not None else \
        [f.measure for f in feas if f.state != FeasibilityState.infeasible]
    blocked = {m.value: f"infeasible: {fmap[m].reason_code}" for m in requested if fmap[m].state == FeasibilityState.infeasible}
    applied = [m for m in requested if m.value not in blocked]

    sim = simulate(baseline, home, applied, a, feas)
    carbon = carbon_change(sim)
    s_before = score_home(home, baseline.gas_kwh, baseline.elec_kwh, _energy_prov(baseline), use_home_baseline=False)
    s_after = None
    if sim.status == ValueStatus.ok:
        done = [r.measure for r in sim.measures if r.status == ValueStatus.ok]
        s_after = score_after(home, done, sim.after.gas_total, sim.after.elec_import)

    standalone = {}
    for m in applied:
        s1 = simulate(baseline, home, [m], a, feas)
        r = s1.measures[0] if s1.measures else None
        c1 = carbon_change(s1)
        standalone[m.value] = {
            "status": (r.status if r else s1.status).value, "reason": (r.reason_code if r else s1.reason_code),
            "gas_saving_kwh": r.gas_saving_kwh if r else None, "elec_saving_kwh": r.elec_saving_kwh if r else None,
            "purchased_saving_kwh": r.purchased_saving_kwh if r else None,
            "carbon_saving_kg": c1.total_kg, "suitability": fmap[m].suitability.value if fmap[m].suitability else None,
            "feasibility": fmap[m].state.value, "reason_text": fmap[m].reason_text,
        }

    pkg = packages_mod.search(home, baseline, feas, a) if request.include_packages else None
    sens = sens_mod.run(home, baseline, feas, pkg, a) if (request.include_sensitivity and pkg is not None) else None

    warnings = list(sim.warnings)
    if baseline.note:
        warnings.append(baseline.note)
    warnings += [f"{m} requested but {why}: no impact computed" for m, why in blocked.items()]
    estimated = [r.measure for r in sim.measures if r.status == ValueStatus.ok]
    warnings += [f"{f.measure.value} applied conditionally: verify {', '.join(f.missing_inputs)}"
                 for f in feas if f.state == FeasibilityState.needs_verification and f.measure in estimated]
    warnings += [f"{r.measure.value} not estimated: {r.reason_code}" for r in sim.measures
                 if r.status in (ValueStatus.not_estimated, ValueStatus.unavailable)]
    if sum(1 for m in estimated if m in FABRIC or m in (MeasureId.double_glazing, MeasureId.smart_thermostat)) >= 2:
        warnings.append(packages_mod.COMBO_WARNING)
    if home.flag_stale_epc:
        warnings.append("latest EPC is older than 10 years; recorded features may be out of date")
    if s_before.status != ValueStatus.ok:
        warnings.append("Green Home Score unavailable: " + "; ".join(s_before.notes))
    if pkg is not None:
        warnings += pkg.fallbacks
    warnings.append("all savings are estimates, not guarantees")
    warnings = list(dict.fromkeys(warnings))

    versions = config.versions()
    sid = scenario_id(home.state_dict(), request, versions)
    assumptions = {**resolve(a).as_dict(), "heat_pump_mode": a.heat_pump_mode.value,
                   "heat_pump_partial_share": a.heat_pump_partial_share, "baseline_scale": a.baseline_scale,
                   "emission_factors": {f: v["kg_co2e_per_kwh"] for f, v in config.emission_factors().items()},
                   "package_threshold_pct": packages_mod.THRESHOLD_PCT}
    aud = audit_mod.build_audit(sid, versions, baseline, feas, sim, pkg, sens, warnings)
    return ScenarioResult(
        scenario_id=sid, home=public_home(home), request=request, baseline=baseline, feasibility=feas,
        measures_applied=applied, measures_blocked=blocked, simulation=sim, standalone=standalone, carbon=carbon,
        score_before=s_before, score_after=s_after, packages=pkg, sensitivity=sens, valuation=valuation(),
        audit=aud, assumptions=assumptions, warnings=warnings, versions=versions,
        data_timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
