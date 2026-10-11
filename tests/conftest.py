import os
import sys
from pathlib import Path

import pytest

# No test ever calls a real LLM provider or writes the shared answer cache, even with keys in .env: tests outside
# tests/llm (e.g. the web API prefetching an LLM explanation in the background) must not spend quota or need the network.
os.environ["LLM_ENABLED"] = "0"
os.environ["LLM_CACHE"] = "0"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.config import HOMES_TAGGED  # noqa: E402
from backend.app.schemas.property import HomeRecord  # noqa: E402

needs_data = pytest.mark.skipif(not HOMES_TAGGED.exists(), reason="built York data not present")

DEMO_A, DEMO_B, DEMO_C = "U100050529765", "A012dcfda4e502be0", "U100050565716"


def make_home(**kw) -> HomeRecord:
    """A complete, gas-heated semi-detached house; override any field."""
    base = dict(
        home_id="T1", split="test", rating="D", sap_score=60.0, property_type="House", built_form="Semi-Detached",
        age_band="1950-1966", age_end=1966.0, floor_area_m2=100.0,
        walls_rating="Average", walls_rating_status="observed", walls_description="Cavity wall, as built, no insulation (assumed)",
        roof_rating="Average", roof_rating_status="observed", roof_description="Pitched, 100 mm loft insulation",
        floor_rating=None, floor_rating_status="not_applicable",
        glazing="double", multi_glaze_pct=100.0, heating_type="gas_boiler", heating_rating="Good", controls="full",
        solar_pv=False, pv_roof_pct=0.0, solar_water_heating=False, wind_turbines=0, mains_gas=True,
        baseline_gas_kwh=12000.0, gas_status="population_benchmark", prov_baseline_gas_kwh="population_benchmark",
        baseline_elec_kwh=3000.0, elec_status="population_benchmark", prov_baseline_elec_kwh="population_benchmark",
    )
    base.update(kw)
    return HomeRecord(**base)
