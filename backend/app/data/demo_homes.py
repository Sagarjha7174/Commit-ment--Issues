"""The three public demo homes, rebuilt without the York data (data/ is not in git).

Used only when data/processed/region=york/homes_tagged.parquet is absent, so the API and the web app run on a fresh
clone. Inputs: the public fields in configs/demo_homes.json plus the few certificate fields that
tests/fixtures/hand_calc_demo.py documents for these homes (SUPPLEMENTS). No address, full postcode or UPRN is used;
the outward code is the only location. Results on these homes reproduce tests/fixtures/scenario_{a,b,c}.json
(tests/unit/test_demo_source.py).
"""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from ..config import CONFIGS
from ..schemas.property import POSTCODE_COLUMN, SOURCE_COLUMNS

# Certificate fields not in demo_homes.json, as documented in tests/fixtures/hand_calc_demo.py:
# A: cavity walls Poor (no insulation), flat roof with limited insulation (loft infeasible, D20), 87% multi-glazed,
#    heating rated Good; B: insulated cavity walls, another dwelling above, 100% double glazed, electric heating
#    rated Very Poor; C: missing data, only the build year is known.
SUPPLEMENTS: dict[str, dict] = {
    "a_poor_gas_house": {
        "raw_walls_description": "Cavity wall, as built, no insulation (assumed)",
        "raw_roof_description": "Flat, limited insulation (assumed)",
        "multi_glaze_pct": 87.0, "heating_rating": "Good", "age_end": 1975.0,
        "raw_photo_supply": 0.0, "raw_solar_water_heating_flag": "N", "raw_wind_turbine_count": 0,
    },
    "b_flat_loft_solar_infeasible": {
        "raw_walls_description": "Cavity wall, as built, insulated (assumed)",
        "raw_roof_description": "(another dwelling above)",
        "multi_glaze_pct": 100.0, "heating_rating": "Very Poor", "age_end": 2006.0,
        "raw_photo_supply": 0.0, "raw_solar_water_heating_flag": "N", "raw_wind_turbine_count": 0,
    },
    "c_missing_data": {"age_end": 2008.0},
}


@lru_cache(maxsize=1)
def demo_config() -> dict:
    return json.loads((CONFIGS / "demo_homes.json").read_text())


def demo_list() -> list[dict]:
    """Public fields only, for the home picker."""
    return [{"home_id": h["home_id"], "case": h["case"], "display_label": h["display_label"],
             "why_chosen": h["why_chosen"], "rating": h["public_fields"].get("rating"),
             "property_type": h["public_fields"].get("property_type"),
             "postcode_outward": h["public_fields"].get("postcode_outward")}
            for h in demo_config()["homes"]]


def demo_rows() -> list[dict]:
    """One homes_tagged-style row per demo home (only the columns the engine reads)."""
    inv = {field: col for col, field in SOURCE_COLUMNS.items()}
    rows = []
    for h in demo_config()["homes"]:
        row: dict = {c: None for c in SOURCE_COLUMNS}
        row["property_id"], row["split"] = h["home_id"], h["split"]
        for k, v in h["public_fields"].items():
            if k in SOURCE_COLUMNS:
                row[k] = v
            elif k in inv:
                row[inv[k]] = v
        row.update(SUPPLEMENTS.get(h["case"], {}))
        row[POSTCODE_COLUMN] = h["public_fields"].get("postcode_outward")   # outward code only
        rows.append(row)
    return rows


def demo_frame() -> pd.DataFrame:
    df = pd.DataFrame(demo_rows())
    return df.set_index("property_id", drop=False)


def display_labels() -> dict[str, str]:
    return {h["home_id"]: h["display_label"] for h in demo_config()["homes"]}
