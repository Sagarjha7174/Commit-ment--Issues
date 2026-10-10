"""End-use decomposition and resolved engine constants. All energy in kWh/year."""
from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..schemas.enums import ImpactLevel
from ..schemas.retrofit import EndUses
from ..schemas.scenario import Assumptions


@dataclass(frozen=True)
class Constants:
    boiler_efficiency: float
    other_gas_share: float
    space_share: float          # of (space + water) gas
    water_share: float
    scop: float
    impact_level: ImpactLevel

    def as_dict(self) -> dict:
        return {"boiler_efficiency": self.boiler_efficiency, "other_gas_share": self.other_gas_share,
                "space_share_of_heat_water_gas": self.space_share, "water_share_of_heat_water_gas": self.water_share,
                "heat_pump_scop": self.scop, "impact_level": self.impact_level.value}


def resolve(a: Assumptions) -> Constants:
    g = config.catalogue_globals()
    space = a.space_share_of_heat_water_gas if a.space_share_of_heat_water_gas is not None else g["space_share_of_heat_water_gas"]
    return Constants(
        boiler_efficiency=a.boiler_efficiency if a.boiler_efficiency is not None else g["boiler_efficiency"],
        other_gas_share=a.other_gas_share if a.other_gas_share is not None else g["other_gas_share"],
        space_share=space,
        water_share=1.0 - space,
        scop=a.heat_pump_scop if a.heat_pump_scop is not None else g["heat_pump_scop"]["mid"],
        impact_level=a.impact_level,
    )


def decompose(gas: float, elec: float, gas_heated: bool, c: Constants) -> EndUses:
    """gas_other = other_share * gas (cooking, never touched); the rest is split space / water.
    A home not heated by gas keeps all its gas as gas_other (no heating end use on gas)."""
    if not gas_heated:
        return EndUses(gas_other=gas, elec_base=elec)
    gas_other = c.other_gas_share * gas
    heat_water = gas - gas_other
    return EndUses(gas_space=c.space_share * heat_water, gas_water=c.water_share * heat_water,
                   gas_other=gas_other, elec_base=elec)


def useful(gas_kwh: float, c: Constants) -> float:
    return gas_kwh * c.boiler_efficiency


def gas_for_useful(useful_kwh: float, c: Constants) -> float:
    return useful_kwh / c.boiler_efficiency
