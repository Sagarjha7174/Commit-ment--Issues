"""Paths and versioned configs for the engine. Every config is read from configs/, never hard-coded."""
from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs"
REGION_DIR = ROOT / "data" / "processed" / "region=york"
HOMES_TAGGED = REGION_DIR / "homes_tagged.parquet"
HOMES_SCORED = REGION_DIR / "homes_scored.parquet"


@lru_cache(maxsize=None)
def _json(name: str) -> dict:
    return json.loads((CONFIGS / name).read_text())


def catalogue() -> dict:
    return _json("retrofit_catalogue.json")


def score_params() -> dict:
    return _json("score_params.json")


def score_mappings() -> dict:
    return _json("score_mappings.json")


def state_effects() -> dict:
    return _json("retrofit_state_effects.json")


def value_gate() -> dict:
    return _json("value_gate.json")


def engine_params() -> dict:
    return _json("engine_params.json")


def _optional_json(name: str) -> dict | None:
    p = CONFIGS / name
    return json.loads(p.read_text()) if p.exists() else None


@lru_cache(maxsize=None)
def electric_heating_split() -> dict | None:
    """Heating share of electricity for electrically heated homes (pipelines/build_electric_heating_split.py).
    Absent -> None: the engine abstains for electric-heated homes (D13 behaviour)."""
    return _optional_json("electric_heating_split.json")


@lru_cache(maxsize=None)
def engine_calibration() -> dict | None:
    """Data-derived calibration (pipelines/build_engine_calibration.py): area elasticity, missing-part priors,
    backfitted segment effects, York reference floor area, baseline spread. Absent -> those refinements stay off."""
    return _optional_json("engine_calibration.json")


@lru_cache(maxsize=None)
def combination_calibration() -> dict | None:
    """NEED-calibrated factors for multi-measure fabric/controls packages (pipelines/build_combination_calibration.py)."""
    return _optional_json("combination_calibration.json")


def model_switch() -> dict | None:
    """Switch file written by the ML owner when a modelled baseline beats the benchmark. Absent -> None."""
    p = CONFIGS / "model_switch.json"
    return json.loads(p.read_text()) if p.exists() else None


@lru_cache(maxsize=None)
def emission_factors() -> dict[str, dict]:
    with open(CONFIGS / "emissions_factors.csv", newline="") as f:
        rows = {r["fuel"]: r for r in csv.DictReader(f)}
    return {
        fuel: {
            "kg_co2e_per_kwh": float(r["kg_co2e_per_kwh"]),
            "units": r["units"],
            "source": r["source_name"],
            "year": r["year"],
        }
        for fuel, r in rows.items()
    }


def catalogue_globals() -> dict:
    g = catalogue()["global"]
    return {
        "boiler_efficiency": g["boiler_efficiency"]["value"],
        "other_gas_share": g["other_gas_share"]["value"],
        "space_share_of_heat_water_gas": g["space_share_of_heat_water_gas"]["value"],
        "water_share_of_heat_water_gas": g["water_share_of_heat_water_gas"]["value"],
        # field-evidence SCOP (engine_params, D24) overrides the catalogue assumption
        "heat_pump_scop": {k: engine_params().get("heat_pump_scop", g["heat_pump_scop"])[k] for k in ("low", "mid", "high")},
    }


def measure_spec(measure_id: str) -> dict:
    for m in catalogue()["measures"]:
        if m["id"] == measure_id:
            return m
    raise KeyError(measure_id)


def versions() -> dict:
    ef = emission_factors()
    return {
        "catalogue": catalogue()["version"],
        "score_params": score_params()["version"],
        "score_mappings": score_mappings()["version"],
        "state_effects": state_effects()["version"],
        "emission_factors": f"DESNZ {ef['elec']['year']}",
        "engine": "engine-v2",
        "engine_params": engine_params()["version"],
        # data-derived refinements: present only once built, so the scenario_id changes when they change
        **{k: v["version"] for k, v in (("electric_heating_split", electric_heating_split()),
                                        ("combination_calibration", combination_calibration()),
                                        ("engine_calibration", engine_calibration())) if v},
    }
