"""Description parsers: real-style EPC strings (as they appear in York certificates) -> expected parse."""
import pytest

from backend.app.ml import parsers as P

WALLS = [
    # description, wall_type, wall_insulation, level, u
    ("Cavity wall, filled cavity", "cavity", "filled_cavity", 2, None),
    ("Cavity wall, as built, insulated (assumed)", "cavity", "insulated", 2, None),
    ("Cavity wall, as built, no insulation (assumed)", "cavity", "none", 0, None),
    ("Cavity wall, as built, partial insulation (assumed)", "cavity", "partial", 1, None),
    ("Cavity wall, with internal insulation", "cavity", "internal", 2, None),
    ("Cavity wall, with external insulation", "cavity", "external", 2, None),
    ("Solid brick, as built, no insulation (assumed)", "solid", "none", 0, None),
    ("Solid brick, with internal insulation", "solid", "internal", 2, None),
    ("Solid brick, with external insulation", "solid", "external", 2, None),
    ("Sandstone or limestone, as built, no insulation (assumed)", "solid", "none", 0, None),
    ("Granite or whinstone, as built, insulated (assumed)", "solid", "insulated", 2, None),
    ("Timber frame, as built, insulated (assumed)", "timber", "insulated", 2, None),
    ("Timber frame, as built, partial insulation (assumed)", "timber", "partial", 1, None),
    ("Timber frame, with additional insulation", "timber", "insulated", 2, None),
    ("System built, as built, no insulation (assumed)", "system", "none", 0, None),
    ("System built, with external insulation", "system", "external", 2, None),
    ("Park home wall, as built", "other", "unknown", None, None),
    ("Average thermal transmittance 0.27 W/m²K", "unknown", "unknown", None, 0.27),
    ("Average thermal transmittance 0.35 W/m??K", "unknown", "unknown", None, 0.35),
    ("Average thermal transmittance = 0.20 W/m?K", "unknown", "unknown", None, 0.20),
    ("SAP05:Walls", "unknown", "unknown", None, None),
    ("", None, None, None, None),
    (None, None, None, None, None),
]


@pytest.mark.parametrize("d,wt,wi,lvl,u", WALLS)
def test_walls(d, wt, wi, lvl, u):
    assert P.wall_type(d) == wt
    assert P.wall_insulation(d) == wi
    assert P.wall_insulation_level(d) == lvl
    assert P.u_value(d) == u


ROOFS = [
    ("Pitched, 200 mm loft insulation", "pitched", 200),
    ("Pitched, 100mm loft insulation", "pitched", 100),
    ("Pitched, 300+ mm loft insulation", "pitched", 300),
    ("Pitched, no insulation (assumed)", "pitched", 0),
    ("Pitched, insulated (assumed)", "pitched", None),
    ("Pitched, limited insulation (assumed)", "pitched", None),
    ("Pitched, insulated at rafters", "rafters", None),
    ("(another dwelling above)", "dwelling_above", None),
    ("(other premises above)", "dwelling_above", None),
    ("Roof room(s), insulated (assumed)", "roof_room", None),
    ("Flat, limited insulation (assumed)", "flat", None),
    ("Thatched, with additional insulation", "thatched", None),
    ("Average thermal transmittance 0.11 W/m²K", "unknown", None),
    ("SAP05:Roof", "unknown", None),
]


@pytest.mark.parametrize("d,rt,mm", ROOFS)
def test_roofs(d, rt, mm):
    assert P.roof_type(d) == rt
    assert P.loft_mm(d) == mm


FLOORS = [
    ("Suspended, no insulation (assumed)", "suspended", 0),
    ("Solid, no insulation (assumed)", "solid", 0),
    ("Solid, limited insulation (assumed)", "solid", 1),
    ("Solid, insulated (assumed)", "solid", 2),
    ("Suspended, insulated", "suspended", 2),
    ("(another dwelling below)", "dwelling_below", None),
    ("(other premises below)", "dwelling_below", None),
    ("To unheated space, uninsulated (assumed)", "exposed", 0),
    ("To external air, insulated (assumed)", "exposed", 2),
    ("Average thermal transmittance 0.15 W/m²K", "unknown", None),
    ("SAP05:Floor", "unknown", None),
]


@pytest.mark.parametrize("d,ft,lvl", FLOORS)
def test_floors(d, ft, lvl):
    assert P.floor_type(d) == ft
    assert P.floor_insulation_level(d) == lvl


FUELS = [
    ("mains gas (not community)", "mains_gas"), ("Gas: mains gas", "mains_gas"), ("mains gas (community)", "mains_gas"),
    ("electricity (not community)", "electricity"), ("Electricity: electricity, unspecified tariff", "electricity"),
    ("oil (not community)", "oil"), ("Oil: heating oil", "oil"), ("B30K (not community)", "oil"),
    ("LPG (not community)", "lpg"), ("Gas: bulk LPG", "lpg"), ("bottled LPG", "lpg"),
    ("house coal (not community)", "solid"), ("dual fuel - mineral + wood", "solid"), ("bulk wood pellets", "solid"),
    ("biomass (community)", "solid"), ("anthracite", "solid"),
    ("To be used only when there is no heating/hot-water system", "other"), (None, None),
]


@pytest.mark.parametrize("d,fuel", FUELS)
def test_main_fuel(d, fuel):
    assert P.main_fuel(d) == fuel


HEATING = [
    ("Boiler and radiators, mains gas", "boiler"), ("Boiler and underfloor heating, mains gas", "boiler"),
    ("Electric storage heaters", "storage_heaters"), ("Room heaters, electric", "room_heaters"),
    ("Community scheme", "community"), ("Community scheme, mains gas", "community"),
    ("Air source heat pump, radiators, electric", "heat_pump"),
    ("Air source heat pump, radiators, electric, Boiler and radiators, mains gas", "heat_pump"),
    ("Boiler and radiators, mains gas, Electric storage heaters", "boiler"),
    ("Electric storage heaters, Room heaters, electric", "storage_heaters"),
    ("Ground source heat pump, underfloor, electric", "heat_pump"), ("Warm air, mains gas", "other"),
    ("Electric underfloor heating", "other"), ("Portable electric heaters assumed for most rooms", "room_heaters"),
    ("No system present: electric heaters assumed", "room_heaters"), ("SAP05:Main-Heating", "other"), (None, None),
]


@pytest.mark.parametrize("d,fam", HEATING)
def test_heating_family(d, fam):
    assert P.heating_family(d) == fam


@pytest.mark.parametrize("d,t", [
    ("Marketed sale", "marketed_sale"), ("marketed sale", "marketed_sale"), ("Non-marketed sale", "non_marketed_sale"),
    ("non marketed sale", "non_marketed_sale"), ("Rental", "rental"), ("rental (private)", "rental_private"),
    ("rental (social)", "rental_social"), ("New dwelling", "new_dwelling"), ("not sale or rental", "other"),
    ("None of the above", "other"), ("ECO assessment", "other"), (None, None),
])
def test_transaction_type(d, t):
    assert P.transaction_type(d) == t


def test_age_mid_year_and_need_band():
    assert P.age_mid_year("before 1900", 1850, 1899) == 1890
    assert P.age_mid_year("1950-1966", 1950, 1966) == 1958
    assert P.age_mid_year("2007 onwards", 2007, 2026) == 2016.5
    assert P.age_mid_year("2103", 2103, 2103) is None
    assert P.age_mid_year(None, None, None) is None
    assert [P.need_age_band(e) for e in (1899, 1929, 1949, 1975, 1990, 2002, 2006, None)] == [1, 1, 2, 2, 3, 3, 4, None]


def test_u_value_rejects_implausible():
    assert P.u_value("Average thermal transmittance 9.9 W/m²K") is None
    assert P.u_value("Pitched, 200 mm loft insulation") is None
