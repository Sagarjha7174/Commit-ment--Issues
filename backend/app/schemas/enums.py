"""Closed enums shared by every service. Adding a value is a schema change."""
from __future__ import annotations

from enum import Enum


class Provenance(str, Enum):
    observed = "observed"                      # read from the EPC / data as recorded
    population_benchmark = "population_benchmark"  # NEED median of similar homes
    user_provided = "user_provided"            # supplied by the customer
    modelled = "modelled"                      # output of a trained model
    assumption = "assumption"                  # documented assumption / proxy
    derived = "derived"                        # computed by the engine from other values
    unavailable = "unavailable"                # missing; value is null
    not_applicable = "not_applicable"          # does not apply to this home


class FeasibilityState(str, Enum):
    feasible = "feasible"
    infeasible = "infeasible"
    needs_verification = "needs_verification"


class Suitability(str, Enum):
    high = "High"
    medium = "Medium"
    low = "Low"


class MeasureId(str, Enum):
    loft_insulation = "loft_insulation"
    cavity_wall = "cavity_wall"
    solid_wall = "solid_wall"
    double_glazing = "double_glazing"
    smart_thermostat = "smart_thermostat"
    heat_pump = "heat_pump"
    solar_pv = "solar_pv"


MEASURE_ORDER: tuple[MeasureId, ...] = (
    MeasureId.loft_insulation,
    MeasureId.cavity_wall,
    MeasureId.solid_wall,
    MeasureId.double_glazing,
    MeasureId.smart_thermostat,
    MeasureId.heat_pump,
    MeasureId.solar_pv,
)
FABRIC = (MeasureId.loft_insulation, MeasureId.cavity_wall, MeasureId.solid_wall)


class ValueStatus(str, Enum):
    ok = "ok"
    unavailable = "unavailable"        # input missing or blocked
    not_estimated = "not_estimated"    # engine abstains (unsupported basis, mode unknown, ...)
    blocked = "blocked"                # infeasible measure requested


class HeatPumpMode(str, Enum):
    full = "full"
    partial = "partial"
    unknown = "unknown"


class CombinationMode(str, Enum):
    engineering = "engineering"            # sequential multiplicative model (default)
    need_calibrated = "need_calibrated"    # multi-measure fabric/controls impacts scaled to NEED combination medians (D17)


class ImpactLevel(str, Enum):
    low = "low"
    mid = "mid"
    high = "high"


def order_measures(ids) -> list[MeasureId]:
    s = {MeasureId(i) for i in ids}
    return [m for m in MEASURE_ORDER if m in s]
