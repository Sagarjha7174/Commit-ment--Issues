import pytest

from backend.app.schemas.enums import FeasibilityState as F, MeasureId as M, Provenance, Suitability
from backend.app.schemas.scenario import UserReading
from backend.app.services import feasibility as fz
from backend.app.services.baseline import get_baseline
from tests.conftest import DEMO_A, DEMO_B, DEMO_C, make_home, needs_data


def st(home, m):
    return fz.as_map(fz.assess(home))[m]


# ---- baseline ----

def test_baseline_priority_user_over_benchmark():
    h = make_home()
    b = get_baseline(h)
    assert (b.gas_kwh, b.elec_kwh, b.source) == (12000.0, 3000.0, "population_benchmark")
    u = get_baseline(h, UserReading(gas_kwh=9000.0))
    assert u.gas_kwh == 9000.0 and u.gas_provenance == Provenance.user_provided and u.elec_kwh == 3000.0 and u.source == "mixed"
    both = get_baseline(h, UserReading(gas_kwh=9000.0, elec_kwh=2500.0))
    assert both.source == "user_provided"


def test_model_baseline_ignored_without_switch():
    b = get_baseline(make_home(), use_model=True)
    assert b.source == "population_benchmark" and "benchmark used" in b.note


def test_missing_baseline_stays_none():
    b = get_baseline(make_home(baseline_gas_kwh=None, gas_status="unknown_mains_gas"))
    assert b.gas_kwh is None and b.gas_provenance == Provenance.unavailable and not b.gas_heated


@pytest.mark.parametrize("flag", ["flag_conflict_gas_heating_no_mains_gas", "flag_energy_zero_or_negative", "flag_no_heating_description"])
def test_blocking_flags(flag):
    assert flag in get_baseline(make_home(**{flag: True})).blocking_flags


def test_gas_heated_only_for_gas_boiler_with_gas():
    assert get_baseline(make_home()).gas_heated
    assert not get_baseline(make_home(heating_type="electric", baseline_gas_kwh=0.0, gas_status="no_mains_gas")).gas_heated


# ---- loft ----

def test_loft_boundary():
    assert st(make_home(roof_rating="Average"), M.loft_insulation).state == F.feasible
    assert st(make_home(roof_rating="Good"), M.loft_insulation).state == F.infeasible
    assert st(make_home(roof_rating="Very Poor"), M.loft_insulation).suitability == Suitability.high


def test_loft_flat_not_top_floor_vs_unknown():
    flat = make_home(property_type="Flat", roof_rating=None, roof_rating_status="not_applicable", roof_description="(another dwelling above)")
    assert st(flat, M.loft_insulation).state == F.infeasible and st(flat, M.loft_insulation).reason_code == "flat_not_top_floor"
    top = make_home(property_type="Flat", roof_rating="Poor")
    assert st(top, M.loft_insulation).state == F.feasible
    unk = make_home(property_type="Flat", roof_rating=None, roof_rating_status="not_applicable", roof_description="SAP05:Roof")
    i = st(unk, M.loft_insulation)
    assert i.state == F.needs_verification and i.missing_inputs == ["roof_rating"]


# ---- walls ----

def test_cavity_age_boundary():
    assert st(make_home(age_end=1999.0), M.cavity_wall).state == F.feasible
    assert st(make_home(age_end=2000.0), M.cavity_wall).state == F.infeasible


def test_cavity_vs_solid_and_rating():
    solid = make_home(walls_description="Solid brick, as built, no insulation (assumed)", walls_rating="Very Poor")
    assert st(solid, M.cavity_wall).state == F.infeasible and st(solid, M.solid_wall).state == F.feasible
    cav = make_home()
    assert st(cav, M.solid_wall).state == F.infeasible and st(cav, M.cavity_wall).state == F.feasible
    good = make_home(walls_rating="Good")
    assert st(good, M.cavity_wall).state == F.infeasible and st(good, M.solid_wall).state == F.infeasible


def test_walls_missing_input_needs_verification():
    h = make_home(walls_description="Average thermal transmittance 0.45 W/m²K", walls_rating="Average")
    assert st(h, M.cavity_wall).state == F.needs_verification and "wall_type" in st(h, M.cavity_wall).missing_inputs
    assert st(h, M.solid_wall).state == F.needs_verification
    h2 = make_home(age_end=None)
    assert st(h2, M.cavity_wall).state == F.needs_verification and st(h2, M.cavity_wall).missing_inputs == ["age_end"]


# ---- glazing / thermostat ----

def test_glazing_boundary():
    assert st(make_home(glazing="single"), M.double_glazing).state == F.feasible
    assert st(make_home(glazing="partial", multi_glaze_pct=60.0), M.double_glazing).state == F.feasible
    assert st(make_home(glazing="double"), M.double_glazing).state == F.infeasible
    assert st(make_home(glazing="triple"), M.double_glazing).state == F.infeasible
    assert st(make_home(glazing=None), M.double_glazing).state == F.needs_verification


def test_thermostat_boundary():
    assert st(make_home(controls="full"), M.smart_thermostat).state == F.feasible
    assert st(make_home(controls="smart"), M.smart_thermostat).state == F.infeasible
    assert st(make_home(controls=None), M.smart_thermostat).state == F.needs_verification


# ---- heat pump / solar ----

def test_heat_pump_rules():
    assert st(make_home(), M.heat_pump).state == F.feasible
    assert st(make_home(heating_type="heat_pump"), M.heat_pump).state == F.infeasible
    flat = st(make_home(property_type="Flat"), M.heat_pump)
    assert flat.state == F.feasible and flat.suitability == Suitability.low
    assert st(make_home(heating_type=None), M.heat_pump).state == F.needs_verification
    assert st(make_home(flag_conflict_gas_heating_no_mains_gas=True), M.heat_pump).state == F.needs_verification


def test_solar_rules():
    assert st(make_home(), M.solar_pv).state == F.feasible
    assert st(make_home(property_type="Flat"), M.solar_pv).state == F.infeasible
    assert st(make_home(property_type="Maisonette"), M.solar_pv).state == F.infeasible
    assert st(make_home(solar_pv=True), M.solar_pv).state == F.infeasible
    assert st(make_home(solar_pv=None), M.solar_pv).state == F.needs_verification
    assert st(make_home(property_type=None), M.solar_pv).state == F.needs_verification


def test_infeasible_has_no_suitability_and_every_item_has_reason():
    for i in fz.assess(make_home(roof_rating="Good", glazing="double")):
        assert i.reason_code and i.reason_text
        if i.state == F.infeasible:
            assert i.suitability is None


# ---- demo homes ----

@needs_data
def test_demo_homes():
    from backend.app.data.loaders import get_home
    a = fz.as_map(fz.assess(get_home(DEMO_A)))
    assert {m for m, i in a.items() if i.state == F.feasible} == {M.loft_insulation, M.cavity_wall, M.double_glazing,
                                                                   M.smart_thermostat, M.heat_pump, M.solar_pv}
    b = fz.as_map(fz.assess(get_home(DEMO_B)))
    assert b[M.loft_insulation].state == F.infeasible and b[M.solar_pv].state == F.infeasible
    assert b[M.heat_pump].suitability == Suitability.low
    c = fz.as_map(fz.assess(get_home(DEMO_C)))
    assert all(i.state == F.needs_verification for i in c.values())
    assert get_baseline(get_home(DEMO_C)).gas_kwh is None
