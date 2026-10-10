"""Map the team engine's ScenarioResult (backend/app/schemas/scenario.py) onto the fact contract the LLM layer
uses (the keys in facts_view / checker / templates / prompts). Only this module knows the engine's shape.

Engine status words map as ok -> available, not_estimated -> not_estimated, unavailable / blocked -> unavailable.
Technical engine warnings are rewritten in plain English for homeowners (the originals stay in the result).
"""

from __future__ import annotations

import re
from typing import Any

from .measures import display_name

_STATUS = {"ok": "available", "not_estimated": "not_estimated", "unavailable": "unavailable", "blocked": "unavailable"}
_PROVENANCE = {"user_provided": "user-provided", "population_benchmark": "population benchmark"}


def is_engine_result(d: Any) -> bool:
    return isinstance(d, dict) and "simulation" in d and "score_before" in d


def _gas_total(e: dict | None) -> float | None:
    return None if not e else e["gas_space"] + e["gas_water"] + e["gas_other"]


def _elec_import(e: dict | None) -> float | None:
    return None if not e else e["elec_base"] + e["hp_elec"] - e["pv_offset"]


def _plain_reason(reason: str | None) -> str | None:
    """Drop internal references ("(docs/... , D14)", "D10") from reasons shown to homeowners."""
    if not reason:
        return reason
    if "gated off" in reason or "value_gate" in reason:
        return "the property-value model has not passed its accuracy checks yet"
    return re.sub(r"\s*\((?:docs/[^)]*|D\d+[^)]*)\)", "", reason).strip()


def plain_warnings(warnings: list[str]) -> list[str]:
    """Rewrite the engine's technical warnings for homeowners; group the per-measure 'not validated' ones."""
    unvalidated: list[str] = []
    out: list[str] = []
    for w in warnings:
        m = re.match(r"^(\w+): impact not validated against NEED", w)
        if m:
            unvalidated.append(display_name(m.group(1)))
        elif w.startswith("electricity use rises"):
            out.append("Electricity bought from the grid goes up with this plan, because a heat pump runs on "
                       "electricity.")
        elif w.startswith("combined fabric/controls savings may be overestimated"):
            pts = re.search(r"by ([\d.]+-[\d.]+) percentage points", w)
            extra = f" (by {pts.group(1).replace('-', ' to ')} percentage points)" if pts else ""
            out.append("Combined insulation and controls savings may be overestimated: in national measured data, "
                       f"real combined savings were lower{extra}.")
        elif w.strip().lower() == "all savings are estimates, not guarantees":
            continue  # every explanation already says this
        else:
            out.append(_plain_reason(w) or w)
    if unvalidated:
        names = unvalidated[0] if len(unvalidated) == 1 else ", ".join(unvalidated[:-1]) + " and " + unvalidated[-1]
        out.insert(0, f"The savings for {names} use typical published ranges, not measured UK data.")
    return out


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


def _package_cost(r: dict) -> tuple[float | None, str, str | None]:
    applied = sorted(r.get("measures_applied") or [])
    for p in ((r.get("packages") or {}).get("packages") or []):
        if sorted(p.get("measures") or []) == applied:
            if p.get("cost_gbp") is not None and p.get("cost_status", "ok") == "ok":
                return p["cost_gbp"], "available", None
            return None, _STATUS.get(p.get("cost_status"), "not_estimated"), "no cost data for these measures"
    return None, "not_estimated", "the cost was not calculated for this selection"


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
    car_ok = car.get("status") == "ok"
    cost, cost_status, cost_reason = _package_cost(r)
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
            "after": ({"gas_kwh": _gas_total(sim.get("after")), "grid_elec_kwh": _elec_import(sim.get("after")),
                       "heat_pump_elec_kwh": (sim.get("after") or {}).get("hp_elec")} if sim_ok else
                      {"gas_kwh": None, "grid_elec_kwh": None, "status": _STATUS.get(sim.get("status"), "unavailable"),
                       "reason": sim_reason}),
            "change": change,
            "per_measure": per_measure,
        },
        "carbon_results": ({"saving_kg": car.get("total_kg"), "factors_version": (r.get("versions") or {})
                            .get("emission_factors")} if car_ok else
                           {"saving_kg": None, "status": _STATUS.get(car.get("status"), "unavailable"),
                            "reason": _plain_reason(car.get("reason_code")) or sim_reason}),
        "cost_results": {"package_cost_gbp": cost, **({} if cost_status == "available" else
                                                       {"package_cost_status": cost_status,
                                                        "package_cost_reason": cost_reason}),
                         "bill_change_gbp": None, "bill_status": "not estimated",
                         "bill_reason": "no tariff assumptions are set"},
        "valuation": ({"status": "exploratory", "uplift_low_pct": val.get("low_pct"), "uplift_high_pct": val.get("high_pct")}
                      if val_ok else {"status": "not_estimated", "uplift_low_pct": None, "uplift_high_pct": None,
                                      "reason": _plain_reason(val.get("reason")) or "not estimated"}),
        "warnings": plain_warnings(list(r.get("warnings") or [])),
        "assumptions": _assumptions(r.get("assumptions") or {}),
        "versions": r.get("versions") or {},
    }
    if out["green_home_score"]["after"] is None:
        del out["green_home_score"]["after"]
    return out
