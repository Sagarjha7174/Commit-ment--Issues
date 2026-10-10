"""Feasibility of each catalogue measure for one home.

States: feasible | infeasible | needs_verification. A missing critical input gives needs_verification, never infeasible.
Rules follow configs/retrofit_catalogue.json applicability_rules; the regexes are read from the catalogue.
ML may only reorder feasible measures; it never overrides these constraints.
"""
from __future__ import annotations

import re
from typing import Optional

from .. import config
from ..schemas.enums import MEASURE_ORDER, FeasibilityState as F, MeasureId, Suitability as Su
from ..schemas.property import HomeRecord
from ..schemas.retrofit import FeasibilityItem

GOOD = {"Good", "Very Good"}
POOR = {"Very Poor", "Poor"}
FLATS = {"Flat", "Maisonette"}
DWELLING_ABOVE = ("another dwelling above", "other premises above", "another premises above", "same dwelling above")


def _item(m: MeasureId, state: F, code: str, text: str, suit: Optional[Su] = None, missing=()) -> FeasibilityItem:
    return FeasibilityItem(measure=m, state=state, suitability=suit if state != F.infeasible else None,
                           reason_code=code, reason_text=text, missing_inputs=list(missing))


def _rules(mid: MeasureId) -> dict:
    return config.measure_spec(mid.value)["applicability_rules"]["requires"]


def _dwelling_above(home: HomeRecord) -> bool:
    d = (home.roof_description or "").strip().lower()
    return any(k in d for k in DWELLING_ABOVE)


def roof_type(home: HomeRecord) -> Optional[str]:
    """Roof type from the EPC roof description (D20): pitched | rafters | flat | roof_room | thatched | dwelling_above |
    unknown (U-value-only or software codes) | None (no description)."""
    d = (home.roof_description or "").strip().lower()
    if not d:
        return None
    if _dwelling_above(home):
        return "dwelling_above"
    if d.startswith("pitched"):
        return "rafters" if "rafter" in d else "pitched"
    if d.startswith("flat"):
        return "flat"
    if d.startswith("roof room"):
        return "roof_room"
    if d.startswith("thatched"):
        return "thatched"
    return "unknown"


def loft_depth_mm(home: HomeRecord) -> Optional[int]:
    """Recorded loft insulation depth for pitched roofs ("Pitched, 100 mm loft insulation"; "no insulation" = 0)."""
    d = (home.roof_description or "").lower()
    m = re.search(r"(\d+)\+?\s*mm", d)
    if m:
        return int(m.group(1))
    if "no insulation" in d:
        return 0
    return None


def _params(key: str) -> dict:
    return config.engine_params().get(key, {})


def loft(home: HomeRecord) -> FeasibilityItem:
    m = MeasureId.loft_insulation
    rt = roof_type(home)
    if home.roof_rating_status == "not_applicable" or home.roof_rating is None:
        if _dwelling_above(home):
            code = "flat_not_top_floor" if home.property_type in FLATS else "dwelling_above"
            return _item(m, F.infeasible, code, "Another dwelling is above this home, so there is no loft to insulate.")
        return _item(m, F.needs_verification, "roof_unknown", "Roof type and insulation are not recorded; a survey must confirm there is a loft.",
                     Su.medium, ["roof_rating"])
    if home.roof_rating in _rules(m)["roof_rating_not_in"]:
        return _item(m, F.infeasible, "already_insulated", f"Roof is already rated {home.roof_rating}.")
    if rt == "flat":
        return _item(m, F.infeasible, "flat_roof", "Flat roof: there is no loft. Flat-roof insulation is a different measure, not in the catalogue.")
    if rt == "roof_room":
        return _item(m, F.needs_verification, "room_in_roof", "Rooms in the roof: at most a small loft void; room-in-roof insulation is a different, costlier measure.",
                     Su.low, ["loft_void"])
    if rt == "rafters":
        return _item(m, F.needs_verification, "insulated_at_rafters", "Roof is insulated at the rafters, so there may be no cold loft floor to insulate.",
                     Su.low, ["loft_floor"])
    if rt == "thatched":
        return _item(m, F.needs_verification, "thatched_roof", "Thatched roof: loft access and fire-safety limits must be checked.", Su.low, ["loft_void"])
    if rt != "pitched":
        return _item(m, F.needs_verification, "roof_type_unknown", "Roof type is not recorded in words (U-value or code only); a survey must confirm a loft.",
                     Su.medium, ["roof_type"])
    p = _params("loft")
    mm = loft_depth_mm(home)
    if mm is not None and mm >= p.get("already_sufficient_mm", 270):
        return _item(m, F.infeasible, "loft_already_deep", f"Loft already has {mm} mm of insulation.")
    high = home.roof_rating in POOR or (mm is not None and mm <= p.get("high_suitability_max_mm", 100))
    depth = f"{mm} mm recorded" if mm is not None else "depth not recorded"
    return _item(m, F.feasible, "roof_below_good", f"Pitched roof rated {home.roof_rating} ({depth}); loft insulation is low cost.",
                 Su.high if high else Su.medium)


def _wall_type(home: HomeRecord) -> Optional[str]:
    d = (home.walls_description or "").strip().lower()
    if not d:
        return None
    if re.search(_rules(MeasureId.cavity_wall)["walls_description_regex"], d):
        return "cavity"
    if re.search(_rules(MeasureId.solid_wall)["walls_description_regex"], d):
        return "solid"
    if d.startswith(("timber frame", "park home")):
        return "other_known"
    return None  # "Average thermal transmittance ...", "SAP05:Walls", system built, basement: type not determinable


def cavity(home: HomeRecord) -> FeasibilityItem:
    m = MeasureId.cavity_wall
    if home.walls_rating in GOOD:
        return _item(m, F.infeasible, "already_insulated", f"Walls are already rated {home.walls_rating}.")
    wt = _wall_type(home)
    if wt in ("solid", "other_known"):
        return _item(m, F.infeasible, "not_cavity_wall", f"Walls are recorded as {home.walls_description!r}, not cavity walls.")
    missing = [k for k, v in (("walls_rating", home.walls_rating), ("wall_type", wt), ("age_end", home.age_end)) if v is None]
    if wt == "cavity" and home.age_end is not None and home.age_end >= _rules(m)["age_end_lt"]:
        return _item(m, F.infeasible, "built_2000_or_later", "Built 2000 or later; cavities were insulated when built.")
    if missing:
        return _item(m, F.needs_verification, "wall_inputs_missing", "Wall type, rating or age is not recorded; a survey must confirm an unfilled cavity.",
                     Su.medium, missing)
    suit = Su.high if home.walls_rating in POOR else Su.medium
    return _item(m, F.feasible, "unfilled_cavity", f"Cavity walls rated {home.walls_rating}, built before 2000.", suit)


def solid(home: HomeRecord) -> FeasibilityItem:
    m = MeasureId.solid_wall
    if home.walls_rating in GOOD:
        return _item(m, F.infeasible, "already_insulated", f"Walls are already rated {home.walls_rating}.")
    wt = _wall_type(home)
    if wt in ("cavity", "other_known"):
        return _item(m, F.infeasible, "not_solid_wall", f"Walls are recorded as {home.walls_description!r}, not solid masonry.")
    missing = [k for k, v in (("walls_rating", home.walls_rating), ("wall_type", wt)) if v is None]
    if missing:
        return _item(m, F.needs_verification, "wall_inputs_missing", "Wall type or rating is not recorded; a survey must confirm solid masonry walls.",
                     Su.low, missing)
    suit = Su.medium if home.walls_rating in POOR else Su.low
    return _item(m, F.feasible, "uninsulated_solid_wall",
                 f"Solid walls rated {home.walls_rating}; effective but costly and disruptive." + _planning_note(home), suit)


def glazing(home: HomeRecord) -> FeasibilityItem:
    m = MeasureId.double_glazing
    if home.glazing is None:
        return _item(m, F.needs_verification, "glazing_unknown", "Glazing is not recorded.", Su.medium, ["glazing"])
    if home.glazing in _rules(m)["glazing_not_in"]:
        return _item(m, F.infeasible, "already_double_or_triple", f"Windows are already {home.glazing} glazed.")
    if home.glazing == "single":
        return _item(m, F.feasible, "single_glazed", "Single glazing throughout.", Su.high)
    pct = home.multi_glaze_pct
    return _item(m, F.feasible, "partly_single_glazed",
                 f"Partly single glazed ({100 - pct:g}% of windows)." if pct is not None else "Partly single glazed.", Su.medium)


def thermostat(home: HomeRecord) -> FeasibilityItem:
    m = MeasureId.smart_thermostat
    if home.controls is None:
        return _item(m, F.needs_verification, "controls_unknown", "Heating controls are not recorded.", Su.medium, ["controls"])
    if home.controls in _rules(m)["controls_not_in"]:
        return _item(m, F.infeasible, "already_smart", "Already has time and temperature zone control (smart proxy).")
    suit = Su.high if home.controls in ("none", "timer") else Su.medium
    return _item(m, F.feasible, f"controls_{home.controls}", f"Current controls: {home.controls}; low-cost upgrade.", suit)


def heat_pump(home: HomeRecord) -> FeasibilityItem:
    m = MeasureId.heat_pump
    if home.heating_type is None:
        return _item(m, F.needs_verification, "heating_unknown", "Main heating is not recorded.", Su.low, ["heating_type"])
    if home.heating_type in _rules(m)["heating_type_not_in"]:
        return _item(m, F.infeasible, "already_heat_pump", "Already heated by a heat pump.")
    if home.heating_type == "gas_boiler" and home.flag_conflict_gas_heating_no_mains_gas:
        return _item(m, F.needs_verification, "gas_supply_conflict", "Gas boiler recorded but no mains gas; heating fuel must be confirmed.",
                     Su.low, ["mains_gas"])
    if home.property_type in FLATS:
        return _item(m, F.feasible, "flat_outdoor_space_unconfirmed", "Flat: space for an outdoor unit is not confirmed.", Su.low)
    fabric_poor = home.walls_rating in POOR or home.roof_rating in POOR
    if fabric_poor:
        return _item(m, F.feasible, "fabric_first", "Feasible; insulate walls/roof first so the heat pump can be smaller.", Su.medium)
    return _item(m, F.feasible, "fabric_adequate", "Feasible; walls and roof are not rated poor.", Su.high)


def solar(home: HomeRecord) -> FeasibilityItem:
    m = MeasureId.solar_pv
    if home.property_type is None:
        return _item(m, F.needs_verification, "property_type_unknown", "Property type is not recorded.", Su.medium, ["property_type"])
    if home.property_type in _rules(m)["property_type_not_in"]:
        return _item(m, F.infeasible, "flat_shared_roof", "Flats and maisonettes have no individual roof for panels.")
    if home.solar_pv is None:
        return _item(m, F.needs_verification, "solar_unknown", "Existing solar PV is not recorded.", Su.medium, ["solar_pv"])
    if home.solar_pv:
        return _item(m, F.infeasible, "already_has_pv", "Already has solar PV.")
    return _item(m, F.feasible, "no_pv", "No PV recorded; roof orientation and shading are not known." + _planning_note(home), Su.medium)


def _planning_note(home: HomeRecord) -> str:
    """D20: York has many conservation areas; pre-1919 homes need a planning check (a note, not a rule: no planning data)."""
    from .impacts import age_segment
    if age_segment(home.age_band) == "Pre 1919":
        return " Note: " + _params("planning").get("pre_1919_note", "check planning constraints") + "."
    return ""


RULES = {
    MeasureId.loft_insulation: loft, MeasureId.cavity_wall: cavity, MeasureId.solid_wall: solid,
    MeasureId.double_glazing: glazing, MeasureId.smart_thermostat: thermostat, MeasureId.heat_pump: heat_pump,
    MeasureId.solar_pv: solar,
}


def assess(home: HomeRecord) -> list[FeasibilityItem]:
    return [RULES[m](home) for m in MEASURE_ORDER]


def as_map(items: list[FeasibilityItem]) -> dict[MeasureId, FeasibilityItem]:
    return {i.measure: i for i in items}
