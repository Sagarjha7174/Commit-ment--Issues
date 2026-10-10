"""Green Home Score: S = sum(w_k * s_k) over seven fixed-weight parts (configs/score_mappings.json).

Rules (docs/SCORE.md):
- each sub-score is 0-100 and never decreases as the home's state improves;
- a missing part is scored 50 for the headline and 0 / 100 for [range_low, range_high]; weights stay fixed;
- more than 2 missing parts -> total unavailable (None + status), never a silent 0;
- the after-retrofit score recomputes only parts whose inputs change; the EPC SAP score is not re-assessed.
"""
from __future__ import annotations

import math
from typing import Optional

from .. import config
from ..schemas.enums import MeasureId, Provenance, ValueStatus
from ..schemas.property import HomeRecord
from ..schemas.scenario import PartScore, ScoreResult

PARTS = ("energy_efficiency", "energy_intensity", "insulation", "heating", "windows", "renewables", "smart_controls")
PART_LABELS = {
    "energy_efficiency": "EPC energy efficiency",
    "energy_intensity": "energy use per m2",
    "insulation": "insulation",
    "heating": "heating system",
    "windows": "windows and glazing",
    "renewables": "renewable energy",
    "smart_controls": "heating controls",
}
DWELLING_ABOVE = ("another dwelling above", "other premises above", "another premises above", "same dwelling above")


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def classify(total: Optional[int]) -> Optional[str]:
    if total is None:
        return None
    for c in config.score_mappings()["classes"]:
        if total >= c["min"]:
            return c["label"]
    raise ValueError(total)


# ---------- part mappings: each returns (sub | None, provenance, status, detail) ----------

def sub_energy_efficiency(home: HomeRecord):
    if home.sap_score is None:
        return None, Provenance.unavailable, "missing", "no SAP score"
    s = min(max(home.sap_score, 0.0), 100.0)
    return s, Provenance.observed, "ok", f"SAP {home.sap_score:g} (EPC band {home.rating})"


def intensity_value(gas: Optional[float], elec: Optional[float], area: Optional[float]) -> Optional[float]:
    if gas is None or elec is None or area is None or area <= 0:
        return None
    return (gas + elec) / area


def sub_from_intensity(x: float) -> float:
    p = config.score_params()["intensity"]
    p10, p90 = p["p10"], p["p90"]
    return min(max(100.0 * (p90 - x) / (p90 - p10), 0.0), 100.0)


def sub_energy_intensity(home: HomeRecord, gas: Optional[float], elec: Optional[float], prov: Provenance):
    if home.flag_conflict_gas_heating_no_mains_gas:
        return None, Provenance.unavailable, "missing", "gas boiler recorded but no mains gas (conflict)"
    if home.floor_area_m2 is None or home.flag_floor_area_implausible:
        return None, Provenance.unavailable, "missing", "floor area missing or implausible"
    x = intensity_value(gas, elec, home.floor_area_m2)
    if x is None:
        miss = "gas" if gas is None else "electricity"
        return None, Provenance.unavailable, "missing", f"{miss} baseline unavailable"
    return sub_from_intensity(x), prov, "ok", f"{x:.1f} kWh/m2/yr"


def _pts(rating: Optional[str]) -> Optional[float]:
    return config.score_mappings()["rating_points"].get(rating) if rating else None


def sub_insulation(home: HomeRecord):
    w = config.score_mappings()["insulation"]["element_weights"]
    used, total_w, acc = [], 0.0, 0.0
    for el, rating, status in (("walls", home.walls_rating, home.walls_rating_status),
                               ("roof", home.roof_rating, home.roof_rating_status),
                               ("floor", home.floor_rating, home.floor_rating_status)):
        p = _pts(rating)
        if status == "not_applicable" or p is None:
            continue
        used.append(f"{el} {rating}")
        total_w += w[el]
        acc += w[el] * p
    if not used:
        return None, Provenance.unavailable, "missing", "no applicable wall/roof/floor rating"
    return acc / total_w, Provenance.observed, "ok", ", ".join(used)


def sub_heating(home: HomeRecord):
    floor = config.score_mappings()["heating"]["heat_pump_floor"]
    p = _pts(home.heating_rating)
    if home.heating_type == "heat_pump":
        if p is None:
            return float(floor), Provenance.assumption, "assumption", "heat pump, rating unknown: heat-pump floor"
        return max(p, floor), Provenance.observed, "ok", f"heat pump, EPC heating {home.heating_rating} (floor {floor})"
    if p is None:
        return None, Provenance.unavailable, "missing", "no heating rating"
    return p, Provenance.observed, "ok", f"{home.heating_type or 'unknown type'}, EPC heating {home.heating_rating}"


def sub_windows(home: HomeRecord):
    m = config.score_mappings()["windows"]
    pts = m["points"]
    if home.glazing is None:
        return None, Provenance.unavailable, "missing", "glazing unknown"
    if home.glazing in pts:
        return float(pts[home.glazing]), Provenance.observed, "ok", f"{home.glazing} glazing"
    if home.glazing == "partial":
        pct, prov, st = home.multi_glaze_pct, Provenance.observed, "ok"
        if pct is None:
            pct, prov, st = m["partial_missing_pct"], Provenance.assumption, "assumption"
        pct = min(max(pct, 0.0), 100.0)
        return pts["single"] + (pts["double"] - pts["single"]) * pct / 100.0, prov, st, f"partial glazing, {pct:g}% multi-glazed"
    return None, Provenance.unavailable, "missing", f"unrecognised glazing {home.glazing!r}"


def sub_renewables(home: HomeRecord):
    m = config.score_mappings()["renewables"]
    if home.solar_pv is None:
        return None, Provenance.unavailable, "missing", "solar PV not recorded"
    s, bits = float(m["none"]), []
    if home.solar_pv:
        large = home.pv_roof_pct is not None and home.pv_roof_pct >= m["pv_large_min_roof_pct"]
        s = float(m["pv_large"] if large else m["pv_some"])
        bits.append(f"solar PV ({home.pv_roof_pct:g}% roof)" if home.pv_roof_pct else "solar PV")
    if home.solar_water_heating:
        s += m["solar_thermal_add"]
        bits.append("solar thermal")
    if home.wind_turbines:
        s += m["wind_add"]
        bits.append("wind turbine")
    return min(s, float(m["cap"])), Provenance.observed, "ok", ", ".join(bits) or "no renewables recorded"


def sub_smart_controls(home: HomeRecord):
    pts = config.score_mappings()["smart_controls"]["points"]
    if home.controls not in pts:
        return None, Provenance.unavailable, "missing", "heating controls unknown"
    return float(pts[home.controls]), Provenance.assumption if home.controls == "smart" else Provenance.observed, "ok", f"controls: {home.controls}"


# ---------- assembly ----------

def score_home(home: HomeRecord, gas: Optional[float] = None, elec: Optional[float] = None,
               energy_provenance: Optional[Provenance] = None, use_home_baseline: bool = True,
               epc_not_reassessed: bool = False, modelled_sap: Optional[tuple[float, str]] = None) -> ScoreResult:
    """Score one home. Intensity uses (gas, elec) if given, else the home's tagged baseline."""
    mp = config.score_mappings()
    weights = mp["weights"]
    if use_home_baseline and gas is None and elec is None:
        from .baseline import benchmark_energy   # same within-band area scaling as the simulator baseline (D21)
        gas, elec, _ = benchmark_energy(home)
        energy_provenance = Provenance.population_benchmark  # elec is always a benchmark; gas is a benchmark or an observed 0
    raw = {
        "energy_efficiency": sub_energy_efficiency(home),
        "energy_intensity": sub_energy_intensity(home, gas, elec, energy_provenance or Provenance.derived),
        "insulation": sub_insulation(home),
        "heating": sub_heating(home),
        "windows": sub_windows(home),
        "renewables": sub_renewables(home),
        "smart_controls": sub_smart_controls(home),
    }
    head = mp["missing"]["headline_sub"]
    lo_sub, hi_sub = mp["missing"]["range_subs"]
    priors = ((config.engine_calibration() or {}).get("missing_part_priors") or {})
    prior_notes = []
    parts, missing = [], []
    lo = hi = 0.0
    for k in PARTS:
        sub, prov, status, detail = raw[k]
        w = weights[k]
        if k == "energy_efficiency" and modelled_sap is not None:
            sub, prov, status, detail = min(max(modelled_sap[0], 0.0), 100.0), Provenance.modelled, "modelled_epc_change", modelled_sap[1]
        elif k == "energy_efficiency" and epc_not_reassessed:
            status, detail = "unchanged_epc_not_reassessed", detail + "; EPC not re-assessed after retrofit"
        if sub is None:
            missing.append(k)
            used = float(head)
            pr = priors.get(k)
            if isinstance(pr, dict):   # renewables: PV is rarer on old certificates
                pr = pr.get("stale_epc" if home.flag_stale_epc else "recent_epc")
            if pr is not None:
                used = float(pr)
                prior_notes.append(f"{k} missing: scored at the train mean {used:.1f} of similar homes (D22)")
            lo += w * lo_sub
            hi += w * hi_sub
        else:
            used = float(sub)
            lo += w * used
            hi += w * used
        parts.append(PartScore(part=k, sub=None if sub is None else round(float(sub), 6), used_sub=used, weight=w,
                               points=w * used, provenance=prov, status=status, detail=detail))
    key_issues = [f"{PART_LABELS[p.part]} ({p.detail})" for p in parts
                  if p.sub is not None and p.sub < mp["key_issue_below"]]
    complete = f"{7 - len(missing)}/7"
    if len(missing) > mp["missing"]["max_missing_parts"]:
        return ScoreResult(status=ValueStatus.unavailable, total=None, raw_total=None, classification=None,
                           range_low=None, range_high=None, completeness=complete, missing_parts=missing,
                           parts=parts, key_issues=key_issues,
                           notes=[f"{len(missing)} parts missing (> {mp['missing']['max_missing_parts']}): score unavailable"])
    raw_total = sum(p.points for p in parts)
    total = round_half_up(raw_total)
    notes = []
    if missing:
        defaulted = len(missing) - len(prior_notes)
        if defaulted:
            notes.append(f"missing parts without a calibrated prior scored {head} for the headline; range uses {lo_sub}/{hi_sub}")
        else:
            notes.append(f"range uses {lo_sub}/{hi_sub} for missing parts")
        notes += prior_notes
    return ScoreResult(status=ValueStatus.ok, total=total, raw_total=raw_total, classification=classify(total),
                       range_low=round_half_up(lo), range_high=round_half_up(hi), completeness=complete,
                       missing_parts=missing, parts=parts, key_issues=key_issues, notes=notes)


# ---------- after-retrofit state ----------

def _at_least(current: Optional[str], target: str, order: list[str]) -> Optional[str]:
    if current is None:
        return None  # a missing state stays missing: a retrofit never turns "unknown" into a score
    if current not in order:
        return current
    return order[max(order.index(current), order.index(target))]


def apply_state_effects(home: HomeRecord, measures: list[MeasureId]) -> HomeRecord:
    eff = config.state_effects()
    order = eff["rating_order"]
    h = home.model_copy(deep=True)
    for m in measures:
        e = eff["effects"][m.value]
        if "roof_rating_at_least" in e:
            h.roof_rating = _at_least(h.roof_rating, e["roof_rating_at_least"], order)
        if "walls_rating_at_least" in e:
            h.walls_rating = _at_least(h.walls_rating, e["walls_rating_at_least"], order)
        if "glazing_at_least" in e and h.glazing is not None:
            g_order = ["single", "partial", "double", "triple"]
            if h.glazing in g_order and g_order.index(h.glazing) < g_order.index(e["glazing_at_least"]):
                h.glazing = e["glazing_at_least"]
                h.multi_glaze_pct = float(e["multi_glaze_pct"])
        if "controls_at_least" in e and h.controls is not None:
            c_order = ["none", "timer", "full", "smart"]
            if h.controls in c_order and c_order.index(h.controls) < c_order.index(e["controls_at_least"]):
                h.controls = e["controls_at_least"]
        if "heating_type" in e and h.heating_type is not None:
            h.heating_type = e["heating_type"]
        if e.get("solar_pv") and h.solar_pv is not None and not h.solar_pv:
            h.solar_pv = True
            h.pv_roof_pct = e.get("pv_roof_pct_if_unknown")
    return h


def score_after(home: HomeRecord, measures: list[MeasureId], gas_after: Optional[float],
                elec_after: Optional[float], use_modelled_epc: bool = False) -> ScoreResult:
    """After-retrofit score. The modelled EPC change (SAP model, D34) is always attached as `epc_change` when the model
    is available; it replaces the EPC part of the headline only when use_modelled_epc is set."""
    from .sap_model import sap_change
    h = apply_state_effects(home, measures)
    ch = sap_change(home, measures)
    modelled = None
    if use_modelled_epc and ch["status"] == ValueStatus.ok.value:
        modelled = (ch["sap_after_indicative"],
                    f"SAP {home.sap_score:g} {ch['sap_change']:+.1f} modelled = {ch['sap_after_indicative']:g} "
                    f"(indicative band {ch['rating_after_indicative']}; {ch['model_version']})")
    res = score_home(h, gas_after, elec_after, energy_provenance=Provenance.derived,
                     use_home_baseline=False, epc_not_reassessed=True, modelled_sap=modelled)
    return res.model_copy(update={"epc_change": ch, "rating_after_indicative": ch["rating_after_indicative"]})
