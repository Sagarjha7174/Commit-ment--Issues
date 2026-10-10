"""TEST DOUBLE for P2's simulator, so the LLM layer can be built before the real
engine exists. It follows plan_final.md's sequential maths (impact bases,
heat pump full mode, solar last) closely enough to produce realistic,
internally consistent scenario results in the agreed contract shape.

It is NOT the engine. Its scores after retrofit are crude fixed bumps. Replace
uses with the real engine (backend.app.llm.engine.run_scenario; synthetic homes in eval/synthetic_homes.py)
wherever possible; it remains for fast unit tests.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.llm.measures import MEASURE_ORDER, ordered  # noqa: E402
from scenario_id import scenario_id  # noqa: E402  (test helper; the real engine has its own)

EF_GAS, EF_ELEC = 0.18231, 0.14395  # DESNZ 2026 kg CO2e/kWh (plan_final decision 4)
BOILER_EFF, SPACE_SHARE, SCOP, OTHER_GAS_SHARE = 0.85, 0.75, 3.0, 0.05
IMPACTS = {  # (impact_basis, impact)
    "loft_insulation": ("total_gas", 0.03),
    "cavity_wall": ("total_gas", 0.12),
    "solid_wall": ("total_gas", 0.17),
    "double_glazing": ("space_heat_demand", 0.10),
    "smart_thermostat": ("space_heat_demand", 0.075),
    "solar_pv": ("total_grid_electricity", 0.12),
}
COSTS = {"loft_insulation": 1000, "cavity_wall": 2500, "solid_wall": 12000, "double_glazing": 7000,
         "smart_thermostat": 250, "heat_pump": 11000, "solar_pv": 6000}
SCORE_BUMP = {"loft_insulation": 3, "cavity_wall": 5, "solid_wall": 6, "double_glazing": 6,
              "smart_thermostat": 3, "heat_pump": 9, "solar_pv": 7}
VERSIONS = {"catalogue_version": "cat-v1-fake", "model_version": "energy-v1-fake", "factors_version": "DESNZ 2026",
            "score_mapping_version": "score-v1"}


def _class(total: int) -> str:
    return ("Highly efficient" if total >= 80 else "Good" if total >= 65 else "Moderate" if total >= 50
            else "Poor" if total >= 30 else "Very poor")


HOMES: dict[str, dict] = {
    "york-demo-poor-semi": {
        "inputs": {"type": "Semi-detached house", "floor_area_m2": 92, "epc_rating": "E", "walls": "Poor",
                   "roof": "Poor", "glazing": "Single", "heating": "Gas boiler", "controls": "Timer only",
                   "solar": False},
        "input_provenance": {"floor_area_m2": "observed", "walls": "observed", "gas_kwh": "modelled",
                             "elec_kwh": "modelled", "hot_water_share": "assumption"},
        "missing_inputs": [],
        "gas": 12000.0, "elec": 4800.0,
        "parts": {"energy_efficiency": 52, "intensity": 45, "insulation": 30, "heating": 55, "glazing": 10,
                  "renewables": 0, "smart": 40},
        "recommended": ["loft_insulation", "cavity_wall", "heat_pump", "solar_pv"],
        "feasibility": {
            "loft_insulation": "feasible", "cavity_wall": "feasible",
            "solid_wall": {"state": "infeasible", "reason_code": "CAVITY_WALLS",
                           "reason": "the walls are cavity walls, so solid wall insulation does not apply"},
            "double_glazing": "feasible", "smart_thermostat": "feasible", "heat_pump": "feasible",
            "solar_pv": "feasible",
        },
        "warnings": ["Gas and electricity use are modelled estimates from the NEED-trained energy model, "
                     "not meter readings."],
        "valuation": {"status": "exploratory", "uplift_low_pct": 1.0, "uplift_high_pct": 4.0,
                      "label": "indicative, not causal"},
    },
    "york-demo-flat": {
        "inputs": {"type": "Flat (mid floor)", "floor_area_m2": 61, "epc_rating": "D", "walls": "Poor",
                   "roof": "Another dwelling above", "glazing": "Single", "heating": "Gas boiler",
                   "controls": "Timer only", "solar": False},
        "input_provenance": {"floor_area_m2": "observed", "gas_kwh": "population benchmark",
                             "elec_kwh": "population benchmark"},
        "missing_inputs": [],
        "gas": 7000.0, "elec": 2600.0,
        "parts": {"energy_efficiency": 60, "intensity": 40, "insulation": 30, "heating": 55, "glazing": 10,
                  "renewables": 0, "smart": 40},
        "recommended": ["cavity_wall", "double_glazing", "smart_thermostat"],
        "feasibility": {
            "loft_insulation": {"state": "infeasible", "reason_code": "NOT_TOP_FLOOR",
                                "reason": "there is another home above this flat, so there is no loft to insulate"},
            "cavity_wall": "feasible",
            "solid_wall": {"state": "infeasible", "reason_code": "CAVITY_WALLS",
                           "reason": "the walls are cavity walls, so solid wall insulation does not apply"},
            "double_glazing": "feasible", "smart_thermostat": "feasible",
            "heat_pump": {"state": "needs_verification", "reason_code": "OUTDOOR_SPACE_UNKNOWN",
                          "reason": "it is not known whether there is outdoor space for the heat pump unit"},
            "solar_pv": {"state": "infeasible", "reason_code": "FLAT_NO_ROOF",
                         "reason": "a mid-floor flat has no individual roof for panels"},
        },
        "warnings": ["Energy use is the NEED population benchmark for this type and EPC band, not this home's "
                     "own readings."],
        "valuation": {"status": "not_estimated", "uplift_low_pct": None, "uplift_high_pct": None,
                      "reason": "too few matched flat sales to validate a price range"},
    },
    "york-demo-missing": {
        "inputs": {"type": "Terraced house", "floor_area_m2": 78, "epc_rating": "D", "walls": None,
                   "roof": "Poor", "glazing": "Double", "heating": "Gas boiler", "controls": "Timer only",
                   "solar": False},
        "input_provenance": {"floor_area_m2": "observed", "gas_kwh": "synthetic", "elec_kwh": "synthetic"},
        "missing_inputs": ["walls"],
        "gas": 10500.0, "elec": 3300.0,
        "parts": {"energy_efficiency": 61, "intensity": 50, "insulation": None, "heating": 55, "glazing": 75,
                  "renewables": 0, "smart": 40},
        "recommended": ["loft_insulation", "smart_thermostat"],
        "feasibility": {
            "loft_insulation": "feasible",
            "cavity_wall": {"state": "needs_verification", "reason_code": "WALL_TYPE_UNKNOWN",
                            "reason": "the wall construction is not recorded"},
            "solid_wall": {"state": "needs_verification", "reason_code": "WALL_TYPE_UNKNOWN",
                           "reason": "the wall construction is not recorded"},
            "double_glazing": {"state": "infeasible", "reason_code": "ALREADY_DOUBLE",
                               "reason": "the home already has double glazing"},
            "smart_thermostat": "feasible", "heat_pump": "feasible", "solar_pv": "feasible",
        },
        "warnings": ["Two months of meter data are missing; the annual figures are annualised from the ten "
                     "available months.",
                     "Wall construction is unknown, so the insulation part of the score uses a neutral value."],
        "valuation": {"status": "not_estimated", "uplift_low_pct": None, "uplift_high_pct": None,
                      "reason": "value is only estimated for the full recommended package"},
    },
    "york-demo-conflict": {
        "inputs": {"type": "Detached house", "floor_area_m2": 120, "epc_rating": "B", "walls": "Good",
                   "roof": "Good", "glazing": "Double", "heating": "Gas boiler", "controls": "Timer only",
                   "solar": True},
        "input_provenance": {"floor_area_m2": "observed", "gas_kwh": "user-provided", "elec_kwh": "user-provided"},
        "missing_inputs": [],
        "gas": 15000.0, "elec": 6000.0,
        "parts": {"energy_efficiency": 84, "intensity": 5, "insulation": 80, "heating": 55, "glazing": 75,
                  "renewables": 60, "smart": 40},
        "recommended": ["smart_thermostat"],
        "feasibility": {
            "loft_insulation": {"state": "infeasible", "reason_code": "ROOF_GOOD",
                                "reason": "the roof insulation is already rated Good"},
            "cavity_wall": {"state": "infeasible", "reason_code": "WALLS_GOOD",
                            "reason": "the walls are already rated Good"},
            "solid_wall": {"state": "infeasible", "reason_code": "WALLS_GOOD",
                           "reason": "the walls are already rated Good"},
            "double_glazing": {"state": "infeasible", "reason_code": "ALREADY_DOUBLE",
                               "reason": "the home already has double glazing"},
            "smart_thermostat": "feasible", "heat_pump": "feasible",
            "solar_pv": {"state": "infeasible", "reason_code": "ALREADY_SOLAR",
                         "reason": "the home already has solar panels"},
        },
        "warnings": ["The EPC rating is B, but the entered energy use per square metre is among the highest "
                     "tenth of York homes; occupancy or the readings may explain the gap."],
        "valuation": {"status": "not_estimated", "uplift_low_pct": None, "uplift_high_pct": None,
                      "reason": "value is only estimated for the full recommended package"},
    },
    "york-demo-nodata": {
        "inputs": {"type": "Bungalow", "floor_area_m2": None, "epc_rating": "F", "walls": "Very Poor",
                   "roof": "Very Poor", "glazing": "Single", "heating": None, "controls": None, "solar": False},
        "input_provenance": {},
        "missing_inputs": ["floor_area_m2", "heating", "controls", "gas_kwh", "elec_kwh"],
        "gas": None, "elec": None,
        "parts": {"energy_efficiency": 25, "intensity": None, "insulation": 10, "heating": None, "glazing": 10,
                  "renewables": 0, "smart": None},
        "recommended": ["loft_insulation"],
        "feasibility": {
            "loft_insulation": "feasible",
            "cavity_wall": {"state": "infeasible", "reason_code": "SOLID_WALLS",
                            "reason": "the walls are solid, so cavity insulation does not apply"},
            "solid_wall": "feasible", "double_glazing": "feasible",
            "smart_thermostat": {"state": "needs_verification", "reason_code": "CONTROLS_UNKNOWN",
                                 "reason": "the current heating controls are not recorded"},
            "heat_pump": {"state": "needs_verification", "reason_code": "HEATING_UNKNOWN",
                          "reason": "the current heating system is not recorded"},
            "solar_pv": "feasible",
        },
        "warnings": ["No energy use is available: the main heating fuel and floor area are missing, so savings, "
                     "carbon and improvement potential are not estimated."],
        "valuation": {"status": "not_estimated", "uplift_low_pct": None, "uplift_high_pct": None,
                      "reason": "floor area is missing"},
    },
}

WEIGHTS = {"energy_efficiency": .25, "intensity": .20, "insulation": .15, "heating": .15, "glazing": .10,
           "renewables": .10, "smart": .05}


def _score(parts: dict) -> dict:
    known = {k: v for k, v in parts.items() if v is not None}
    mid = sum(WEIGHTS[k] * (v if v is not None else 50) for k, v in parts.items())
    lo = sum(WEIGHTS[k] * (v if v is not None else 0) for k, v in parts.items())
    hi = sum(WEIGHTS[k] * (v if v is not None else 100) for k, v in parts.items())
    total = int(round(mid))
    return {
        "total": total, "class": _class(total), "range": [int(round(lo)), int(round(hi))],
        "completeness": f"{len(known)}/7",
    }, {k: {"sub": v, "weight": WEIGHTS[k], "points": None if v is None else round(WEIGHTS[k] * v, 2),
            **({} if v is not None else {"status": "unavailable", "reason": "input missing; scored at 50 in the "
                                                                            "headline number"})}
        for k, v in parts.items()}


def run(property_id: str, measures: list[str] | None = None) -> dict:
    """Return a scenario result for the home with the given measures (None = recommended plan)."""
    home = HOMES[property_id]
    feas = {m: (v if isinstance(v, str) else v["state"]) for m, v in home["feasibility"].items()}
    chosen = ordered(home["recommended"] if measures is None else measures)
    blocked = [m for m in chosen if feas.get(m) == "infeasible"]
    chosen = [m for m in chosen if m not in blocked]  # infeasible measures are never applied

    before, parts = _score(home["parts"])
    after_total = min(100, before["total"] + sum(SCORE_BUMP[m] for m in chosen))
    state = {"property_id": property_id, "inputs": home["inputs"], "input_provenance": home["input_provenance"],
             "baseline": {"gas": home["gas"], "elec": home["elec"]}, "measures": chosen, **VERSIONS,
             "assumptions": {"boiler_eff": BOILER_EFF, "space_share": SPACE_SHARE, "scop": SCOP,
                             "other_gas_share": OTHER_GAS_SHARE}}
    result = {
        "scenario_id": scenario_id(state),
        "baseline_id": f"{property_id}-base-v1",
        "property_id": property_id,
        "data_timestamp": "2026-10-10",
        "inputs": copy.deepcopy(home["inputs"]),
        "input_provenance": copy.deepcopy(home["input_provenance"]),
        "missing_inputs": list(home["missing_inputs"]),
        "selected_measures": chosen,
        "blocked_measures": blocked,
        "feasibility": copy.deepcopy(home["feasibility"]),
        "green_home_score": {"before": before,
                             "after": {"total": after_total, "class": _class(after_total)},
                             "parts": parts},
        "assumptions": ["75/25 heating and hot water split of gas", "boiler efficiency 85%",
                        "heat pump efficiency 3.0 (range 2.5 to 3.5)", "5% of gas used for cooking and other uses"],
        "warnings": list(home["warnings"]),
        "valuation": copy.deepcopy(home["valuation"]),
        "cost_results": {"package_cost_gbp": float(sum(COSTS[m] for m in chosen)), "bill_change_gbp": None,
                         "bill_status": "not estimated",
                         "bill_reason": "no tariff assumptions are set"},
        **VERSIONS,
        "validation_status": "not_validated",
    }
    if home["gas"] is None or home["elec"] is None:
        reason = "baseline energy use is unknown"
        result["energy_results"] = {
            "baseline": {"grid_elec_kwh": None, "gas_kwh": None, "status": "unavailable", "reason": reason},
            "after": {"grid_elec_kwh": None, "gas_kwh": None, "status": "unavailable", "reason": reason},
            "change": {"grid_elec_saving_kwh": None, "gas_saving_kwh": None, "purchased_saving_kwh": None,
                       "improvement_potential_pct": None, "status": "unavailable", "reason": reason},
            "per_measure": [],
        }
        result["carbon_results"] = {"saving_kg": None, "status": "unavailable", "reason": reason,
                                    "factors_version": VERSIONS["factors_version"]}
        return result

    gas, elec = home["gas"], home["elec"]
    gas_other = OTHER_GAS_SHARE * gas
    gas_space = (gas - gas_other) * SPACE_SHARE
    useful_space = gas_space * BOILER_EFF
    useful_water = (gas - gas_other) * (1 - SPACE_SHARE) * BOILER_EFF
    hp_elec, solar_offset, replaced = 0.0, 0.0, 0.0

    def fuels() -> tuple[float, float]:
        g = gas_other + (1 - replaced) * (useful_space + useful_water) / BOILER_EFF
        return g, elec + hp_elec - solar_offset

    per_measure = []
    for m in chosen:
        g0, e0 = fuels()
        if m in IMPACTS and IMPACTS[m][0] != "total_grid_electricity":
            basis, impact = IMPACTS[m]
            frac = min(impact * gas / gas_space, 1.0) if basis == "total_gas" else impact
            useful_space *= 1 - frac
        elif m == "heat_pump":
            replaced = 1.0
            hp_elec = (useful_space + useful_water) / SCOP
        elif m == "solar_pv":
            solar_offset = IMPACTS[m][1] * (elec + hp_elec)
        g1, e1 = fuels()
        per_measure.append({"measure": m, "gas_saving_kwh": round(g0 - g1, 1), "elec_saving_kwh": round(e0 - e1, 1),
                            "impact_source": "population benchmark (NEED)" if m in ("loft_insulation", "cavity_wall",
                                                                                   "solid_wall", "solar_pv")
                            else "assumption (brief range, not validated)"})
    gas_after, grid_after = fuels()
    gas_saving, elec_saving = gas - gas_after, elec - grid_after
    purchased = gas + elec
    result["energy_results"] = {
        "baseline": {"grid_elec_kwh": elec, "gas_kwh": gas, "useful_space_heat_kwh": round(gas_space * BOILER_EFF, 1),
                     "useful_hot_water_kwh": round((gas - gas_other) * (1 - SPACE_SHARE) * BOILER_EFF, 1)},
        "after": {"grid_elec_kwh": round(grid_after, 1), "gas_kwh": round(gas_after, 1),
                  "heat_pump_elec_kwh": round(hp_elec, 1)},
        "change": {"grid_elec_saving_kwh": round(elec_saving, 1), "gas_saving_kwh": round(gas_saving, 1),
                   "purchased_saving_kwh": round(gas_saving + elec_saving, 1),
                   "improvement_potential_pct": round(100 * (gas_saving + elec_saving) / purchased, 1)},
        "per_measure": per_measure,
    }
    result["carbon_results"] = {"saving_kg": round(gas_saving * EF_GAS + elec_saving * EF_ELEC, 1),
                                "factors_version": VERSIONS["factors_version"]}
    return result


def all_measures() -> tuple[str, ...]:
    return MEASURE_ORDER
