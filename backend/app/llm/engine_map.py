"""Map the team engine's ScenarioResult (backend/app/schemas/scenario.py) onto the fact contract the LLM layer
uses (the keys in facts_view / checker / templates / prompts). Only this module knows the engine's shape.

Engine status words map as ok -> available, not_estimated -> not_estimated, unavailable / blocked -> unavailable.
Technical engine warnings are rewritten in plain English for homeowners (the originals stay in the result).
"""

from __future__ import annotations

import re
from typing import Any

from .measures import MEASURE_ORDER, display_name, ordered
MEASURE_IDS = set(MEASURE_ORDER)
from .payload import build_payload

_STATUS = {"ok": "available", "not_estimated": "not_estimated", "unavailable": "unavailable", "blocked": "unavailable"}
_PROVENANCE = {"user_provided": "user-provided", "population_benchmark": "population benchmark"}


def is_engine_result(d: Any) -> bool:
    return isinstance(d, dict) and "simulation" in d and "score_before" in d


# Engine reason codes in plain English (homeowners never see a code).
REASONS = {
    "baseline_gas_unavailable": "the home's starting gas use is not known",
    "baseline_elec_unavailable": "the home's starting electricity use is not known",
    "baseline_unavailable": "the home's starting energy use is not known",
    "heating_not_on_gas": "the home is not heated by gas, and savings for other heating are not modelled in this version",
    "no_gas_to_displace": "there is no gas heating for a heat pump to replace, and electric-to-heat-pump savings are "
                          "not modelled in this version",
    "heat_pump_mode_unknown": "it is not known how much of the heating the heat pump would cover",
    "impact_basis_unsupported": "there is no supported way to estimate it",
    "no measures applied": "no measure's effect could be estimated",
    "no measures applied: no change in EPC score to value": "no measure's effect on the EPC score could be estimated",
}


def _plain_reason(reason: str | None) -> str | None:
    """Engine codes in plain English; drop internal references ("(docs/... , D14)", "D10")."""
    if not reason:
        return reason
    if reason in REASONS:
        return REASONS[reason]
    if "gated off" in reason or "value_gate" in reason or "value gate closed" in reason:
        return "the property-value model has not passed its accuracy checks yet"
    if reason.startswith("EPC change not estimated: "):
        return _plain_reason(reason.split(": ", 1)[1])
    if "not seen in training sales" in reason:
        return "there are no past York sales in this postcode area to estimate a pound value from"
    if reason.startswith("SAP model not available"):
        return "the EPC score model is not available"
    return re.sub(r"\s*\((?:docs/[^)]*|D\d+[^)]*|run [^)]*)\)", "", reason).strip()


def plain_warnings(warnings: list[str]) -> list[str]:
    """Rewrite the engine's technical warnings for homeowners; group the per-measure ones."""
    unvalidated: list[str] = []
    not_estimated: dict[str, list[str]] = {}
    out: list[str] = []
    # the baseline note joins several notes with "; " (benchmark, electric heating): split only those
    parts = [p.strip() for w in warnings
             for p in (w.split("; ") if ("NEED benchmark:" in w or "electric heating" in w) else [w]) if p.strip()]
    for w in parts:
        m = re.match(r"^(\w+): impact not validated against NEED", w)
        ne = re.match(r"^(\w+) not estimated: (\w+)$", w)
        if m:
            unvalidated.append(display_name(m.group(1)))
        elif ne and ne.group(1) in MEASURE_IDS:
            not_estimated.setdefault(ne.group(2), []).append(display_name(ne.group(1)))
        elif w.startswith("electricity use rises"):
            out.append("Electricity bought from the grid goes up with this plan, because a heat pump runs on "
                       "electricity.")
        elif w.startswith("combined fabric/controls savings may be overestimated"):
            pts = re.search(r"by ([\d.]+-[\d.]+) percentage points", w)
            extra = f" (by {pts.group(1).replace('-', ' to ')} percentage points)" if pts else ""
            out.append("Combined insulation and controls savings may be overestimated: in national measured data, "
                       f"real combined savings were lower{extra}.")
        elif w.startswith("NEED benchmark: median of similar homes"):
            out.append("The starting energy use is a benchmark: the typical use of similar homes in the region, not "
                       "this home's meter readings.")
        elif w.startswith("baseline_gas_unavailable: no energy estimates") or w.startswith("baseline unavailable: no packages"):
            if "No energy, carbon or cost savings can be estimated, because the home's starting energy use is not known." not in out:
                out.append("No energy, carbon or cost savings can be estimated, because the home's starting energy use "
                           "is not known.")
        elif w.startswith("baseline ") and w.endswith(" unavailable"):
            what = w[len("baseline "):-len(" unavailable")].replace("electricity", "electricity use").replace("gas and", "gas and")
            out.append(f"The home's starting {what} is not known.")
        elif w.startswith("Green Home Score unavailable"):
            out.append("The Green Home Score is not available, because too many parts of it have no data.")
        elif w.startswith("electric heating savings not estimated"):
            out.append("Savings for electrically heated homes are not modelled in this version.")
        elif w.strip().lower() == "all savings are estimates, not guarantees":
            continue  # every explanation already says this
        else:
            out.append(_plain_reason(w) or w)
    for code, names in not_estimated.items():
        joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        out.append(f"The savings for {joined} are not estimated, because {REASONS.get(code, code.replace('_', ' '))}.")
    if unvalidated:
        names = unvalidated[0] if len(unvalidated) == 1 else ", ".join(unvalidated[:-1]) + " and " + unvalidated[-1]
        out.insert(0, f"The savings for {names} use typical published ranges, not measured UK data.")
    return list(dict.fromkeys(out))


def _assumptions(a: dict) -> list[str]:
    out = []
    if a.get("space_share_of_heat_water_gas") is not None:
        sp = round(100 * a["space_share_of_heat_water_gas"])
        out.append(f"{sp}/{100 - sp} split of heating and hot-water gas")
    if a.get("boiler_efficiency") is not None:
        out.append(f"boiler efficiency {round(100 * a['boiler_efficiency'])}%")
    if a.get("heat_pump_scop") is not None:
        out.append(f"heat pump efficiency {a['heat_pump_scop']}")
    if a.get("other_gas_share") is not None:
        out.append(f"{round(100 * a['other_gas_share'], 1)}% of gas used for cooking and other uses")
    if a.get("impact_level"):
        out.append(f"{a['impact_level']} retrofit impact estimates")
    return out


def to_contract(r: dict) -> dict:
    """Engine ScenarioResult (as dict) -> the scenario contract facts_view understands."""
    sim, car, sb, sa = r["simulation"], r["carbon"], r["score_before"], r.get("score_after")
    home, base = r.get("home") or {}, r.get("baseline") or {}
    sim_ok = sim.get("status") == "ok"
    sim_reason = _plain_reason(sim.get("reason_code")) or "baseline energy use is unknown"

    def score_block(s: dict | None) -> dict:
        if not s:
            return {"total": None, "status": "unavailable", "reason": "no measures selected"}
        ok = s.get("status") == "ok"
        block = {"total": s.get("total") if ok else None, "class": s.get("classification"),
                 "completeness": s.get("completeness")}
        if s.get("range_low") is not None and s.get("range_high") is not None:
            block["range"] = [s["range_low"], s["range_high"]]
        if not ok:
            block.update(status=_STATUS.get(s.get("status"), "unavailable"), reason="key inputs are missing")
        return block

    feas = {}
    missing_inputs: set[str] = set()
    for f in r.get("feasibility") or []:
        feas[f["measure"]] = {"state": f["state"], "reason": f.get("reason_text"), "reason_code": f.get("reason_code")}
        if f["state"] == "needs_verification":
            missing_inputs |= set(f.get("missing_inputs") or [])
    missing_inputs |= {p for p in (sb.get("missing_parts") or [])}

    change: dict[str, Any]
    if sim_ok:
        ip_ok = sim.get("improvement_potential_status") == "ok"
        change = {"gas_saving_kwh": sim.get("gas_saving_kwh"), "grid_elec_saving_kwh": sim.get("elec_saving_kwh"),
                  "purchased_saving_kwh": sim.get("purchased_saving_kwh"),
                  "improvement_potential_pct": sim.get("improvement_potential_pct") if ip_ok else None}
        if not ip_ok:
            change["improvement_potential_status"] = _STATUS.get(sim.get("improvement_potential_status"), "unavailable")
            change["improvement_potential_reason"] = _plain_reason(sim.get("improvement_potential_reason"))
    else:
        change = {"gas_saving_kwh": None, "grid_elec_saving_kwh": None, "purchased_saving_kwh": None,
                  "improvement_potential_pct": None, "status": _STATUS.get(sim.get("status"), "unavailable"),
                  "reason": sim_reason}
    per_measure = [{"measure": m["measure"], "gas_saving_kwh": m.get("gas_saving_kwh"),
                    "elec_saving_kwh": m.get("elec_saving_kwh")}
                   for m in (sim.get("measures") or []) if m.get("status") == "ok"] if sim_ok else []
    none_estimated = sim_ok and bool(r.get("measures_applied")) and not per_measure
    if none_estimated:   # measures applied, but the engine could not estimate any of them (e.g. D13): not a zero
        codes = [m.get("reason_code") for m in sim.get("measures") or [] if m.get("reason_code")]
        why = _plain_reason(codes[0]) if codes else "the measures' effects could not be estimated"
        change = {"gas_saving_kwh": None, "grid_elec_saving_kwh": None, "purchased_saving_kwh": None,
                  "improvement_potential_pct": None, "status": "not_estimated", "reason": why}
    car_ok = car.get("status") == "ok"
    pay = build_payload(r)            # every number below is an engine value from the payload (no arithmetic here)
    pk = pay["package"]
    val = r.get("valuation") or {}
    val_ok = val.get("status") == "ok"

    out: dict[str, Any] = {
        "scenario_id": r["scenario_id"],
        "property_id": home.get("home_id") or (r.get("request") or {}).get("home_id"),
        "data_timestamp": r.get("data_timestamp"),
        "inputs": {"type": " ".join(x for x in (home.get("built_form"), home.get("property_type")) if x) or None,
                   "floor_area_m2": home.get("floor_area_m2"), "epc_rating": home.get("rating"),
                   "walls": home.get("walls_rating"), "roof": home.get("roof_rating"), "glazing": home.get("glazing"),
                   "heating": (home.get("heating_type") or "").replace("_", " ") or None,
                   "controls": home.get("controls"), "solar": home.get("solar_pv"), "age_band": home.get("age_band")},
        "input_provenance": {"gas_kwh": _PROVENANCE.get(base.get("gas_status"), base.get("gas_status")),
                             "elec_kwh": _PROVENANCE.get(base.get("elec_status"), base.get("elec_status"))},
        "missing_inputs": sorted(missing_inputs),
        "selected_measures": list(r.get("measures_applied") or []),
        "feasibility": feas,
        "green_home_score": {
            "before": score_block(sb), "after": score_block(sa) if r.get("measures_applied") else None,
            "parts": {p["part"]: {"sub": p.get("sub"), "weight": p["weight"],
                                  "points": p.get("points") if p.get("sub") is not None else None}
                      for p in (sb.get("parts") or [])},
        },
        "key_issues": list(sb.get("key_issues") or []),
        "energy_results": {
            "baseline": {"gas_kwh": base.get("gas_kwh"), "grid_elec_kwh": base.get("elec_kwh")},
            "after": ({"gas_kwh": pk["gas_after_kwh"], "grid_elec_kwh": pk["elec_after_kwh"],
                       "heat_pump_elec_kwh": pk["heat_pump_elec_kwh"]} if sim_ok else
                      {"gas_kwh": None, "grid_elec_kwh": None, "status": _STATUS.get(sim.get("status"), "unavailable"),
                       "reason": sim_reason}),
            "change": change,
            "per_measure": per_measure,
        },
        "estimated_measures": [m["measure"] for m in per_measure],
        "carbon_results": ({"saving_kg": None, "status": "not_estimated", "reason": change.get("reason")}
                           if none_estimated else
                           {"saving_kg": car.get("total_kg"), "after_kg": car.get("after_kg"), "factors_version": (r.get("versions") or {})
                            .get("emission_factors"),
                            **({"calibrated_saving_kg": pay["calibrated"]["carbon_saving_kg"]}
                               if pay["calibrated"] and len(r.get("measures_applied") or []) > 1 else {})} if car_ok else
                           {"saving_kg": None, "status": _STATUS.get(car.get("status"), "unavailable"),
                            "reason": _plain_reason(car.get("reason_code")) or sim_reason}),
        "cost_results": _cost_block(pay, none_estimated, change.get("reason")),
        "epc_change": _epc_block(pay),
        "valuation": _value_block(val, val_ok),
        "ranking": [{"measure": display_name(x["measure"]), "assessor_relevance_prob": x["assessor_relevance_prob"]}
                    for x in pay["recommendation"]["ranking"]],
        "standalone": [{"measure": display_name(m), **{k: v for k, v in row.items() if k not in ("status", "reason")}}
                       for m, row in pay["measures"].items() if row.get("status") == "ok"],
        "packages": _featured_block(pay),
        "warnings": plain_warnings(list(r.get("warnings") or [])),
        "assumptions": _assumptions(r.get("assumptions") or {}),
        "versions": r.get("versions") or {},
    }
    unc = pay["uncertainty"]
    if unc and unc.get("status") == "ok":
        out["uncertainty"] = {k: unc.get(k) for k in (
            "carbon_saving_kg_p10", "carbon_saving_kg_p90", "bill_saving_gbp_p10", "bill_saving_gbp_p90",
            "prob_bill_falls", "prob_carbon_cut_ge_threshold")}
    out["priority_measures"] = [x["measure"] for x in pay["recommendation"]["ranking"]]
    out["priority_verify"] = [x["measure"] for x in pay["recommendation"]["ranking"] if x.get("verify")]
    out["payload_values"] = pay["values"]
    if out["epc_change"] is None:
        del out["epc_change"]
    if not out["packages"]:
        del out["packages"]
    if out["green_home_score"]["after"] is None:
        del out["green_home_score"]["after"]
    return out


def _cost_block(pay: dict, none_estimated: bool = False, why: str | None = None) -> dict:
    """Costs, grants, payback, bills and the illustrative loan, as the engine computed them (D26, D27)."""
    pk, fin = pay["package"], pay["finance"]
    out: dict[str, Any] = {}
    if none_estimated:
        return {"package_cost_gbp": None, "package_cost_status": "not_estimated",
                "package_cost_reason": why or "the measures' effects could not be estimated",
                "bill_saving_gbp": None, "bill_saving_status": "not_estimated",
                "bill_saving_reason": why or "not estimated"}
    if pk["measures"]:
        out.update(package_cost_gbp=pk["gross_cost_gbp"], grants_gbp=pk["grants_gbp"], net_cost_gbp=pk["net_cost_gbp"])
        if pk["gross_cost_gbp"] is None:
            out.update(package_cost_status="not_estimated", package_cost_reason="no cost data for these measures")
        out["payback_years"] = pk["payback_years"]
        if pk["payback_years"] is None:
            why = ("the annual bill does not fall with these measures, so there is no payback"
                   if pk["bill_status"] == "ok" else "the change in the annual bill is not estimated")
            out.update(payback_years_status="not_estimated", payback_years_reason=why)
    if pk["bill_status"] == "ok":
        out.update(bill_before_gbp=pk["bill_before_gbp"], bill_after_gbp=pk["bill_after_gbp"],
                   bill_saving_gbp=pk["bill_saving_gbp"])
    else:
        out.update(bill_saving_gbp=None, bill_saving_status="not_estimated",
                   bill_saving_reason="the energy figures needed for a bill estimate are not available")
    if pk["measures"] and fin.get("loan_monthly_repayment_gbp") is not None:
        out.update(loan_monthly_repayment_gbp=fin["loan_monthly_repayment_gbp"],
                   monthly_bill_saving_gbp=fin["monthly_bill_saving_gbp"], loan_apr_pct=fin["loan_apr_pct"],
                   loan_term_years=fin["loan_term_years"])
    return out


def _epc_block(pay: dict) -> dict | None:
    ch = pay["epc_change"]
    if not ch.get("status"):
        return None
    if ch["status"] == "ok":
        return {"sap_before": ch["sap_before"], "sap_change": ch["sap_change"],
                "sap_after_indicative": ch["sap_after_indicative"], "rating_before": ch["rating_before"],
                "rating_after_indicative": ch["rating_after_indicative"]}
    return {"sap_change": None, "status": "not_estimated", "reason": _plain_reason(ch.get("reason")) or "not modelled"}


def _value_block(val: dict, ok: bool) -> dict:
    if not ok:
        return {"status": "not_estimated", "uplift_low_pct": None, "uplift_high_pct": None,
                "reason": _plain_reason(val.get("reason")) or "not estimated"}
    out = {"status": "exploratory", "uplift_low_pct": val.get("low_pct"), "uplift_mid_pct": val.get("mid_pct"),
           "uplift_high_pct": val.get("high_pct")}
    if val.get("value_status") == "ok":
        out.update(current_value_gbp=val.get("current_value_gbp"), current_value_low_gbp=val.get("current_value_low_gbp"),
                   current_value_high_gbp=val.get("current_value_high_gbp"))
    else:
        out.update(current_value_gbp=None, current_value_status="not_estimated",
                   current_value_reason=_plain_reason(val.get("value_reason")) or "not estimated")
    return out


def _featured_block(pay: dict) -> dict:
    out = {}
    for obj, f in pay["featured"].items():
        if not f.get("package_id"):
            continue
        out[obj] = {"label": f["label"], "measures": ", ".join(display_name(m) for m in ordered(f["measures"])),
                    "net_cost_gbp": f["net_cost_gbp"], "carbon_saving_kg": f["carbon_saving_kg"],
                    "bill_saving_gbp": f["bill_saving_gbp"], "payback_years": f["payback_years"]}
        if f.get("calibrated_carbon_saving_kg") is not None:
            out[obj]["calibrated_carbon_saving_kg"] = f["calibrated_carbon_saving_kg"]
    return out
