"""Sequential retrofit simulator (docs/ENGINE.md).

Fixed order: fabric (loft, cavity, solid wall) -> double glazing -> smart thermostat -> heat pump -> solar PV.
Each measure acts on the state left by the previous one, so reductions multiply (15% then 20% = 32%).
Every step is logged with per-end-use deltas; per-fuel totals must equal the sum of the logged steps.
Saving = before - after; an increase is a negative saving.
"""
from __future__ import annotations

from typing import Optional

from .. import config
from ..schemas.enums import FABRIC, CombinationMode, FeasibilityState, HeatPumpMode, MeasureId, ValueStatus, order_measures
from ..schemas.property import HomeRecord
from ..schemas.retrofit import EndUses, FeasibilityItem, MeasureRow, SimResult, SimStep
from ..schemas.scenario import Assumptions, Baseline
from . import impacts, units
from .baseline import blocking_reasons
from .feasibility import as_map, assess

TOL = 1e-6
SUPPORTED_BASES = {"total_gas", "space_heat_demand", "total_grid_electricity"}
FABRIC_CONTROLS = (*FABRIC, MeasureId.double_glazing, MeasureId.smart_thermostat)


def _impact(spec: dict, level) -> float:
    return float(spec["impact"][level.value])


def total_gas_to_space_fraction(eu: EndUses, impact: float) -> tuple[float, float]:
    """NEED impact is a % of the whole-home gas: kWh saved = impact x current total gas, expressed as a fraction
    of the current space-heating gas (capped at 1)."""
    kwh_saved = impact * eu.gas_total
    return kwh_saved, min(kwh_saved / eu.gas_space, 1.0)


def reduce_space_heat(eu: EndUses, frac: float, c: units.Constants) -> EndUses:
    """Cut useful space heat by frac; gas follows through the boiler efficiency."""
    new = eu.model_copy()
    new.gas_space = units.gas_for_useful(units.useful(eu.gas_space, c) * (1 - frac), c)
    return new


def reduce_electric_space_heat(eu: EndUses, frac: float) -> EndUses:
    """Electric heating delivers its electricity as heat, so electricity falls in proportion (D16)."""
    new = eu.model_copy()
    new.elec_space = eu.elec_space * (1 - frac)
    return new


def combination_factor(measures: list[MeasureId], c: units.Constants) -> tuple[float, Optional[str]]:
    """NEED-calibrated scaling of fabric/controls impacts when a package has two or more of them (D17).
    Returns (1.0, None) in engineering mode, for single measures, or when no calibration is built."""
    if c.combination_mode != CombinationMode.need_calibrated:
        return 1.0, None
    combo = sorted(m.value for m in measures if m in FABRIC_CONTROLS)
    if len(combo) < 2:
        return 1.0, None
    cal = config.combination_calibration()
    if cal is None:
        return 1.0, "combination calibration not built: engineering estimate used"
    for row in cal["combinations"]:
        if sorted(row["measures"]) == combo:
            return float(row["factor"]), f"NEED-calibrated: {row['combination']} factor {row['factor']:.3f}"
    return float(cal["pooled_factor"]), f"NEED-calibrated: pooled factor {cal['pooled_factor']:.3f} (no exact NEED combination)"


def _apply(m: MeasureId, eu: EndUses, home: HomeRecord, baseline: Baseline, c: units.Constants, a: Assumptions,
           combo_factor: float = 1.0):
    """Return (after, status, reason_code, impact_used, basis, note). Never mutates eu."""
    spec = config.measure_spec(m.value)
    basis = spec["impact_basis"]
    new = eu.model_copy()
    gas_heated, elec_heated = baseline.gas_heated, baseline.elec_heated

    if m == MeasureId.heat_pump:
        if gas_heated and (eu.gas_space + eu.gas_water) > 0:
            fuel = "gas"
        elif elec_heated and (eu.elec_space + eu.elec_water) > 0:
            fuel = "electric"
        else:
            reason = "no_gas_to_displace" if not elec_heated else "no_heating_left_to_displace"
            return eu, ValueStatus.not_estimated, reason, None, basis, "no metered heating fuel to displace (not gas-heated; electric split unavailable)"
        if a.heat_pump_mode == HeatPumpMode.unknown:
            return eu, ValueStatus.not_estimated, "heat_pump_mode_unknown", None, basis, "heat pump coverage unknown: engine abstains"
        share = 1.0
        if a.heat_pump_mode == HeatPumpMode.partial:
            if a.heat_pump_partial_share is None or not (0 < a.heat_pump_partial_share <= 1):
                return eu, ValueStatus.not_estimated, "partial_share_missing", None, basis, "partial mode needs a share in (0, 1]"
            share = a.heat_pump_partial_share
        if fuel == "gas":
            replaced_useful = share * units.useful(eu.gas_space + eu.gas_water, c)
            new.gas_space = eu.gas_space * (1 - share)
            new.gas_water = eu.gas_water * (1 - share)
            src = f"boiler efficiency {c.boiler_efficiency:.2f}; cooking gas stays"
        else:
            replaced_useful = share * (eu.elec_space + eu.elec_water) * units.electric_efficiency()
            new.elec_space = eu.elec_space * (1 - share)
            new.elec_water = eu.elec_water * (1 - share)
            src = "electric heating efficiency 1.0 (D16)"
        new.hp_elec = eu.hp_elec + replaced_useful / c.scop
        note = (f"{a.heat_pump_mode.value} mode: {share:.0%} of {fuel} space+water heat moved to a heat pump "
                f"(useful {replaced_useful:,.0f} kWh / SCOP {c.scop}; {src})")
        return new, ValueStatus.ok, None, c.scop, "heat_pump_scop", note

    if basis not in SUPPORTED_BASES:
        return eu, ValueStatus.not_estimated, "impact_basis_unsupported", None, basis, f"basis {basis!r} not supported"
    impact, seg = impacts.impact(m.value, c.impact_level.value, home, c.segment_impacts)
    seg_note = (f" [segment-adjusted from headline {seg['headline']:.2%} by {seg['adjustment']:+.2%} (D15)]"
                if seg is not None else "")

    if basis == "total_grid_electricity":
        grid = eu.elec_gross
        new.pv_offset = eu.pv_offset + impact * grid
        return new, ValueStatus.ok, None, impact, basis, f"{impact:.2%} of grid electricity ({grid:,.0f} kWh incl. any heat pump){seg_note}"

    # space-heating measures (fabric, glazing, controls)
    if m in FABRIC_CONTROLS and combo_factor != 1.0:
        impact *= combo_factor
        seg_note += f" x NEED combination factor {combo_factor:.3f} (D17)"
    if gas_heated:
        if eu.gas_space <= 0:
            return eu, ValueStatus.not_estimated, "no_gas_space_heat_left", None, basis, "no gas space heating left to reduce"
        if basis == "total_gas":
            kwh_saved, frac = total_gas_to_space_fraction(eu, impact)
            note = f"{impact:.2%} of total gas ({eu.gas_total:,.0f} kWh) = {kwh_saved:,.0f} kWh -> {frac:.2%} of space-heat gas"
        else:
            frac, note = _space_demand_fraction(m, impact, home)
        return reduce_space_heat(eu, frac, c), ValueStatus.ok, None, impact, basis, note + seg_note
    if elec_heated:
        if eu.elec_space <= 0:
            return eu, ValueStatus.not_estimated, "no_electric_space_heat_left", None, basis, "no electric space heating left to reduce"
        if basis == "total_gas":
            # NEED % of a gas home's total gas, re-expressed as a share of space heat with the same end-use split
            frac = min(impact / c.space_share_of_total_gas, 1.0)
            note = (f"{impact:.2%} of whole-home heating fuel (NEED, gas homes) = {frac:.2%} of space heat "
                    f"(space share {c.space_share_of_total_gas:.4f}); applied to electric space heating")
        else:
            frac, note = _space_demand_fraction(m, impact, home)
            note += "; applied to electric space heating"
        return reduce_electric_space_heat(eu, frac), ValueStatus.ok, None, impact, basis, note + seg_note
    return eu, ValueStatus.not_estimated, "heating_not_on_gas", None, basis, "space heating is not on gas and no electric heating split is available (D13/D16)"


def _space_demand_fraction(m: MeasureId, impact: float, home: HomeRecord) -> tuple[float, str]:
    frac = impact
    note = f"{impact:.2%} of space-heat demand"
    if m == MeasureId.double_glazing and home.glazing == "partial":
        unglazed = 1 - (home.multi_glaze_pct if home.multi_glaze_pct is not None else 50.0) / 100
        frac = impact * unglazed
        note += f" x {unglazed:.0%} single-glazed share"
    return frac, note


def simulate(baseline: Baseline, home: HomeRecord, measures, assumptions: Optional[Assumptions] = None,
             feasibility: Optional[list[FeasibilityItem]] = None) -> SimResult:
    a = assumptions or Assumptions()
    c = units.resolve(a, home)
    ordered = order_measures(measures)
    fmap = as_map(feasibility if feasibility is not None else assess(home))
    cat_validated = {m["id"]: m["validated"] for m in config.catalogue()["measures"]}

    if baseline.gas_kwh is None or baseline.elec_kwh is None:
        miss = "baseline_gas_unavailable" if baseline.gas_kwh is None else "baseline_elec_unavailable"
        rows = [MeasureRow(measure=m, status=ValueStatus.unavailable, reason_code=miss) for m in ordered]
        return SimResult(status=ValueStatus.unavailable, reason_code=miss, measures=rows,
                         improvement_potential_status=ValueStatus.unavailable, improvement_potential_reason=miss,
                         assumptions=c.as_dict(), warnings=[f"{miss}: no energy estimates"])

    gas, elec = baseline.gas_kwh * a.baseline_scale, baseline.elec_kwh * a.baseline_scale
    start = units.decompose(gas, elec, baseline.gas_heated, c, baseline.elec_heat_share if baseline.elec_heated else None)
    eu = start
    steps, rows, warnings = [], [], []
    applicable = [m for m in ordered if fmap[m].state != FeasibilityState.infeasible]
    factor, factor_note = combination_factor(applicable, c)
    if factor_note:
        warnings.append(factor_note)
    for m in ordered:
        f = fmap[m]
        if f.state == FeasibilityState.infeasible:
            steps.append(SimStep(measure=m, status=ValueStatus.blocked, reason_code=f.reason_code, before=eu, after=eu,
                                 gas_saving_kwh=0.0, elec_saving_kwh=0.0, note="infeasible: not applied"))
            rows.append(MeasureRow(measure=m, status=ValueStatus.blocked, reason_code=f.reason_code))
            continue
        after, status, reason, impact, basis, note = _apply(m, eu, home, baseline, c, a, factor)
        if f.state == FeasibilityState.needs_verification and status == ValueStatus.ok:
            note += "; conditional: needs verification (" + ", ".join(f.missing_inputs) + ")"
        ds_gas = eu.gas_total - after.gas_total
        ds_elec = eu.elec_import - after.elec_import
        steps.append(SimStep(measure=m, status=status, reason_code=reason, impact_used=impact, impact_basis=basis,
                             before=eu, after=after, gas_saving_kwh=ds_gas, elec_saving_kwh=ds_elec, note=note))
        if status == ValueStatus.ok:
            rows.append(MeasureRow(measure=m, status=status, gas_saving_kwh=ds_gas, elec_saving_kwh=ds_elec,
                                   purchased_saving_kwh=ds_gas + ds_elec, impact_used=impact, impact_basis=basis,
                                   validated_impact=cat_validated[m.value]))
            if not cat_validated[m.value]:
                warnings.append(f"{m.value}: impact not validated against NEED (brief range / assumption)")
        else:
            rows.append(MeasureRow(measure=m, status=status, reason_code=reason, impact_basis=basis))
        eu = after

    gas_saving = sum(s.gas_saving_kwh for s in steps)
    elec_saving = sum(s.elec_saving_kwh for s in steps)
    # reconciliation: each fuel's total change equals the sum of its logged steps
    assert abs(gas_saving - (start.gas_total - eu.gas_total)) <= TOL * max(1.0, start.gas_total), "gas does not reconcile"
    assert abs(elec_saving - (start.elec_import - eu.elec_import)) <= TOL * max(1.0, start.elec_import), "electricity does not reconcile"
    assert abs(eu.gas_other - start.gas_other) <= TOL, "cooking gas must never change"

    before_p, after_p = start.purchased, eu.purchased
    ip, ip_status, ip_reason = None, ValueStatus.ok, None
    blocks = blocking_reasons(baseline)
    if blocks:
        ip_status, ip_reason = ValueStatus.unavailable, "blocked: " + "; ".join(blocks)
    elif before_p <= 0:
        ip_status, ip_reason = ValueStatus.unavailable, "baseline purchased energy is zero"
    elif ordered and not any(r.status == ValueStatus.ok for r in rows):
        ip_status, ip_reason = ValueStatus.not_estimated, "no requested measure could be estimated for this home"
    else:
        ip = 100.0 * (before_p - after_p) / before_p
    if elec_saving < -TOL:
        warnings.append("electricity use rises (negative electricity saving), e.g. after a heat pump")
    return SimResult(status=ValueStatus.ok, before=start, after=eu, steps=steps, measures=rows,
                     gas_saving_kwh=gas_saving, elec_saving_kwh=elec_saving, purchased_saving_kwh=gas_saving + elec_saving,
                     purchased_before_kwh=before_p, purchased_after_kwh=after_p, improvement_potential_pct=ip,
                     improvement_potential_status=ip_status, improvement_potential_reason=ip_reason,
                     warnings=sorted(set(warnings)), assumptions=c.as_dict())
