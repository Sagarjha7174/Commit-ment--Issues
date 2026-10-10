"""SYNTHETIC test homes for running the real engine without the York data (data/ is not in git).

Each is a HomeRecord built by hand to cover a situation the brief tests: a poor gas house, a mid-floor flat,
missing wall data, no baseline at all, a conflicting EPC-vs-use record, an electric home, an already-good home,
a home with a missing heating system. They are not real properties; results on them show the LLM layer works
with the real engine, not real-world accuracy.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.schemas.property import HomeRecord  # noqa: E402

_BASE = dict(
    split="test", rating="D", sap_score=60.0, property_type="House", built_form="Semi-Detached",
    age_band="1950-1966", age_end=1966.0, floor_area_m2=95.0,
    walls_rating="Average", walls_rating_status="observed", walls_description="Cavity wall, as built, no insulation (assumed)",
    roof_rating="Average", roof_rating_status="observed", roof_description="Pitched, 100 mm loft insulation",
    floor_rating=None, floor_rating_status="not_applicable",
    glazing="double", multi_glaze_pct=100.0, heating_type="gas_boiler", heating_rating="Good", controls="full",
    solar_pv=False, pv_roof_pct=0.0, solar_water_heating=False, wind_turbines=0, mains_gas=True,
    baseline_gas_kwh=12000.0, gas_status="population_benchmark", prov_baseline_gas_kwh="population_benchmark",
    baseline_elec_kwh=3000.0, elec_status="population_benchmark", prov_baseline_elec_kwh="population_benchmark",
)

HOMES: dict[str, dict] = {
    "syn-poor-semi": dict(rating="E", sap_score=45.0, walls_rating="Poor", roof_rating="Poor", glazing="single",
                          multi_glaze_pct=0.0, controls="timer", heating_rating="Average", baseline_gas_kwh=14000.0),
    "syn-flat-mid": dict(property_type="Flat", built_form="Mid-Terrace", floor_area_m2=58.0, roof_rating=None,
                         roof_rating_status="not_applicable", roof_description="(another dwelling above)",
                         walls_rating="Poor", glazing="single", multi_glaze_pct=0.0, controls="timer",
                         baseline_gas_kwh=7000.0, baseline_elec_kwh=2400.0),
    "syn-missing-walls": dict(walls_rating=None, walls_rating_status="missing", walls_description=None,
                              controls=None, roof_rating="Poor", baseline_gas_kwh=10500.0),
    "syn-no-baseline": dict(rating="F", sap_score=30.0, baseline_gas_kwh=None, gas_status="unavailable",
                            prov_baseline_gas_kwh="unavailable", baseline_elec_kwh=None, elec_status="unavailable",
                            prov_baseline_elec_kwh="unavailable", floor_area_m2=None, walls_rating="Very Poor",
                            roof_rating="Very Poor", glazing="single", multi_glaze_pct=0.0),
    "syn-conflict": dict(rating="B", sap_score=84.0, built_form="Detached", floor_area_m2=120.0, walls_rating="Good",
                         roof_rating="Good", controls="timer", solar_pv=True, pv_roof_pct=40.0,
                         baseline_gas_kwh=24000.0, baseline_elec_kwh=6500.0, gas_status="user_provided",
                         prov_baseline_gas_kwh="user_provided", elec_status="user_provided",
                         prov_baseline_elec_kwh="user_provided"),
    "syn-electric-terrace": dict(built_form="Mid-Terrace", mains_gas=False, heating_type="electric_storage",
                                 heating_rating="Poor", baseline_gas_kwh=0.0, baseline_elec_kwh=7800.0,
                                 walls_rating="Poor", age_band="1900-1929", age_end=1929.0,
                                 walls_description="Solid brick, as built, no insulation (assumed)"),
    "syn-good-detached": dict(rating="B", sap_score=82.0, built_form="Detached", walls_rating="Good",
                              roof_rating="Very Good", glazing="triple", controls="smart", solar_pv=True,
                              pv_roof_pct=60.0, baseline_gas_kwh=9000.0),
    "syn-conflict-flat": dict(rating="B", sap_score=81.0, property_type="Flat", built_form="End-Terrace",
                              floor_area_m2=55.0, roof_rating=None, roof_rating_status="not_applicable",
                              walls_rating="Good", controls="timer", baseline_gas_kwh=16000.0,
                              baseline_elec_kwh=5200.0, gas_status="user_provided", prov_baseline_gas_kwh="user_provided",
                              elec_status="user_provided", prov_baseline_elec_kwh="user_provided"),
    "syn-no-elec": dict(baseline_elec_kwh=None, elec_status="unavailable", prov_baseline_elec_kwh="unavailable",
                        walls_rating="Poor", roof_rating="Poor", glazing="single", multi_glaze_pct=0.0),
    "syn-heating-unknown": dict(heating_type=None, heating_rating=None, flag_no_heating_description=True,
                                walls_rating="Poor", baseline_gas_kwh=11000.0),
}


def get(home_id: str) -> HomeRecord:
    if home_id not in HOMES:
        raise KeyError(home_id)
    return HomeRecord(home_id=home_id, display_label=f"Synthetic test home {home_id}", **{**_BASE, **HOMES[home_id]})


def run(home_id: str, measures: list[str] | None = None) -> dict:
    """Engine runner over the synthetic homes (same signature as the fake engine's run)."""
    from backend.app.llm.engine import run_scenario, set_home_source

    set_home_source(get)
    return run_scenario(home_id, measures)
