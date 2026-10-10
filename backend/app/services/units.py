"""End-use decomposition and resolved engine constants. All energy in kWh/year."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .. import config
from ..schemas.enums import CombinationMode, ImpactLevel
from ..schemas.property import HomeRecord
from ..schemas.retrofit import EndUses
from ..schemas.scenario import Assumptions

NEED_TYPE = {"Detached": "Detached", "Semi-Detached": "Semi detached", "End-Terrace": "End terrace",
             "Enclosed End-Terrace": "End terrace", "Mid-Terrace": "Mid terrace", "Enclosed Mid-Terrace": "Mid terrace"}
NEED_EPC = {"A": "A/B", "B": "A/B", "C": "C", "D": "D", "E": "E", "F": "F/G", "G": "F/G"}


@dataclass(frozen=True)
class Constants:
    boiler_efficiency: float
    other_gas_share: float
    space_share: float          # of (space + water) heating energy
    water_share: float
    scop: float
    impact_level: ImpactLevel
    boiler_efficiency_source: str = "catalogue default"
    segment_impacts: bool = True
    combination_mode: CombinationMode = CombinationMode.engineering

    @property
    def space_share_of_total_gas(self) -> float:
        """Share of a gas-heated home's total gas used for space heating (what NEED % of total gas applies to)."""
        return self.space_share * (1 - self.other_gas_share)

    def as_dict(self) -> dict:
        return {"boiler_efficiency": self.boiler_efficiency, "boiler_efficiency_source": self.boiler_efficiency_source,
                "other_gas_share": self.other_gas_share,
                "space_share_of_heat_water_gas": self.space_share, "water_share_of_heat_water_gas": self.water_share,
                "heat_pump_scop": self.scop, "impact_level": self.impact_level.value,
                "segment_impacts": self.segment_impacts, "combination_mode": self.combination_mode.value}


def boiler_efficiency(home: Optional[HomeRecord]) -> tuple[float, str]:
    """Existing boiler's seasonal efficiency from its EPC heating rating (D18); default when unknown."""
    p = config.engine_params()["boiler_efficiency_by_heating_rating"]
    if home is not None and home.heating_type == p["applies_to"] and home.heating_rating in p["values"]:
        return float(p["values"][home.heating_rating]), f"assumption: heating rating {home.heating_rating} (D18)"
    return float(p["default"]), "assumption: default (heating rating unknown or not a gas boiler)"


def resolve(a: Assumptions, home: Optional[HomeRecord] = None) -> Constants:
    g = config.catalogue_globals()
    space = a.space_share_of_heat_water_gas if a.space_share_of_heat_water_gas is not None else g["space_share_of_heat_water_gas"]
    if a.boiler_efficiency is not None:
        eff, eff_src = a.boiler_efficiency, "scenario override"
    elif home is not None:
        eff, eff_src = boiler_efficiency(home)
    else:
        eff, eff_src = g["boiler_efficiency"], "catalogue default"
    return Constants(
        boiler_efficiency=eff,
        other_gas_share=a.other_gas_share if a.other_gas_share is not None else g["other_gas_share"],
        space_share=space,
        water_share=1.0 - space,
        scop=a.heat_pump_scop if a.heat_pump_scop is not None else g["heat_pump_scop"]["mid"],
        impact_level=a.impact_level,
        boiler_efficiency_source=eff_src,
        segment_impacts=a.segment_impacts,
        combination_mode=a.combination_mode,
    )


# ---------- electrically heated homes (D16) ----------

def need_keys(home: HomeRecord) -> tuple[Optional[str], Optional[str]]:
    """NEED property type and EPC band for a home (same mapping as docs/data_york/mappings)."""
    if home.property_type in ("Flat", "Maisonette"):
        ptype = "Flat"
    elif home.property_type == "Bungalow":
        ptype = "Bungalow"
    elif home.property_type == "House":
        ptype = NEED_TYPE.get(home.built_form or "")
    else:
        ptype = None
    return ptype, NEED_EPC.get(home.rating or "")


def electric_heating_share(home: HomeRecord) -> tuple[Optional[float], str]:
    """Share of an electrically heated home's electricity used for space + water heating, or None (engine abstains).

    From NEED benchmarks: 1 - (median electricity of gas-heated homes) / (median electricity of non-gas-heated homes)
    in the same property type x EPC band cell, falling back to the EPC band, then to all homes."""
    eh = config.engine_params()["electric_heating"]
    if home.heating_type not in eh["heating_types"]:
        return None, "not electrically heated"
    split = config.electric_heating_split()
    if split is None:
        return None, "electric heating split not built (run pipelines/build_electric_heating_split.py)"
    ptype, band = need_keys(home)
    for key, label in ((f"{ptype}|{band}", "type x EPC band"), (f"*|{band}", "EPC band"), ("*|*", "all homes")):
        row = split["shares"].get(key)
        if row is not None and row.get("share") is not None:
            return float(row["share"]), f"NEED benchmark split ({label}, {split['version']})"
    return None, "no electric heating split for this home's segment"


def decompose(gas: float, elec: float, gas_heated: bool, c: Constants, elec_heat_share: Optional[float] = None) -> EndUses:
    """Gas-heated: gas_other = other_share * gas (cooking, never touched); the rest is split space / water.
    Electrically heated with a known split: that share of electricity is split space / water, the rest stays elec_base.
    Otherwise all gas is gas_other and all electricity elec_base (no heating end use estimated)."""
    if gas_heated:
        gas_other = c.other_gas_share * gas
        heat_water = gas - gas_other
        return EndUses(gas_space=c.space_share * heat_water, gas_water=c.water_share * heat_water,
                       gas_other=gas_other, elec_base=elec)
    if elec_heat_share is not None:
        heat = elec_heat_share * elec
        return EndUses(gas_other=gas, elec_space=c.space_share * heat, elec_water=c.water_share * heat,
                       elec_base=elec - heat)
    return EndUses(gas_other=gas, elec_base=elec)


def useful(gas_kwh: float, c: Constants) -> float:
    return gas_kwh * c.boiler_efficiency


def gas_for_useful(useful_kwh: float, c: Constants) -> float:
    return useful_kwh / c.boiler_efficiency


def electric_efficiency() -> float:
    return float(config.engine_params()["electric_heating"]["efficiency"])
