"""Canonical home record used by the engine. Built from homes_tagged.parquet column names.

Never carries address, full postcode, UPRN or certificate number: only an outward postcode and a display label.
Missing values stay None (with their provenance); they are never filled with 0.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import Provenance

# homes_tagged.parquet column -> HomeRecord field (only these are read; address columns are never loaded)
SOURCE_COLUMNS: dict[str, str] = {
    "property_id": "home_id",
    "split": "split",
    "rating": "rating",
    "sap_score": "sap_score",
    "property_type": "property_type",
    "built_form": "built_form",
    "age_band": "age_band",
    "age_end": "age_end",
    "floor_area_m2": "floor_area_m2",
    "flag_floor_area_implausible": "flag_floor_area_implausible",
    "walls_rating": "walls_rating",
    "walls_rating_status": "walls_rating_status",
    "raw_walls_description": "walls_description",
    "roof_rating": "roof_rating",
    "roof_rating_status": "roof_rating_status",
    "raw_roof_description": "roof_description",
    "floor_rating": "floor_rating",
    "floor_rating_status": "floor_rating_status",
    "glazing": "glazing",
    "multi_glaze_pct": "multi_glaze_pct",
    "heating_type": "heating_type",
    "heating_rating": "heating_rating",
    "controls": "controls",
    "solar_pv": "solar_pv",
    "raw_photo_supply": "pv_roof_pct",
    "raw_solar_water_heating_flag": "solar_water_heating",
    "raw_wind_turbine_count": "wind_turbines",
    "mains_gas": "mains_gas",
    "baseline_gas_kwh": "baseline_gas_kwh",
    "gas_status": "gas_status",
    "prov_baseline_gas_kwh": "prov_baseline_gas_kwh",
    "baseline_elec_kwh": "baseline_elec_kwh",
    "elec_status": "elec_status",
    "prov_baseline_elec_kwh": "prov_baseline_elec_kwh",
    "benchmark_cell_level": "benchmark_cell_level",
    "flag_conflict_gas_heating_no_mains_gas": "flag_conflict_gas_heating_no_mains_gas",
    "flag_energy_zero_or_negative": "flag_energy_zero_or_negative",
    "flag_no_heating_description": "flag_no_heating_description",
    "flag_stale_epc": "flag_stale_epc",
    "epc_age_years": "epc_age_years",
    "prov_glazing": "prov_glazing",
    "prov_heating_type": "prov_heating_type",
    "prov_solar_pv": "prov_solar_pv",
    "prov_controls": "prov_controls",
    "prov_smart_controls": "prov_smart_controls",
}
POSTCODE_COLUMN = "postcode"  # read only to derive the outward code, then dropped


class HomeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    home_id: str
    display_label: str = ""
    postcode_outward: Optional[str] = None
    split: Optional[str] = None
    rating: Optional[str] = None
    sap_score: Optional[float] = None
    property_type: Optional[str] = None
    built_form: Optional[str] = None
    age_band: Optional[str] = None
    age_end: Optional[float] = None
    floor_area_m2: Optional[float] = None
    flag_floor_area_implausible: bool = False
    walls_rating: Optional[str] = None
    walls_rating_status: Optional[str] = None
    walls_description: Optional[str] = None
    roof_rating: Optional[str] = None
    roof_rating_status: Optional[str] = None
    roof_description: Optional[str] = None
    floor_rating: Optional[str] = None
    floor_rating_status: Optional[str] = None
    glazing: Optional[str] = None
    multi_glaze_pct: Optional[float] = None
    heating_type: Optional[str] = None
    heating_rating: Optional[str] = None
    controls: Optional[str] = None
    solar_pv: Optional[bool] = None
    pv_roof_pct: Optional[float] = None
    solar_water_heating: Optional[bool] = None
    wind_turbines: Optional[int] = None
    mains_gas: Optional[bool] = None
    baseline_gas_kwh: Optional[float] = None
    gas_status: Optional[str] = None
    prov_baseline_gas_kwh: Optional[str] = None
    baseline_elec_kwh: Optional[float] = None
    elec_status: Optional[str] = None
    prov_baseline_elec_kwh: Optional[str] = None
    benchmark_cell_level: Optional[str] = None
    flag_conflict_gas_heating_no_mains_gas: bool = False
    flag_energy_zero_or_negative: bool = False
    flag_no_heating_description: bool = False
    flag_stale_epc: bool = False
    epc_age_years: Optional[float] = None
    prov_glazing: Optional[str] = None
    prov_heating_type: Optional[str] = None
    prov_solar_pv: Optional[str] = None
    prov_controls: Optional[str] = None
    prov_smart_controls: Optional[str] = None
    provenance: dict[str, Provenance] = Field(default_factory=dict)

    def state_dict(self) -> dict:
        """Canonical, JSON-safe state used for hashing (no timestamps)."""
        return self.model_dump(mode="json", exclude={"display_label"})


def _clean(v: Any) -> Any:
    if v is None:
        return None
    try:
        if v is getattr(__import__("pandas"), "NA"):
            return None
    except Exception:  # pragma: no cover
        pass
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):  # numpy scalar
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    return v


def _to_bool(v: Any) -> Optional[bool]:
    v = _clean(v)
    if v is None:
        return None
    if isinstance(v, str):
        return {"Y": True, "N": False}.get(v.strip().upper())
    return bool(v)


def _to_float(v: Any) -> Optional[float]:
    v = _clean(v)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def home_from_row(row: dict) -> HomeRecord:
    d: dict[str, Any] = {}
    for col, field in SOURCE_COLUMNS.items():
        d[field] = _clean(row.get(col))
    for b in ("solar_pv", "mains_gas", "solar_water_heating"):
        d[b] = _to_bool(d[b])
    for f in ("flag_floor_area_implausible", "flag_conflict_gas_heating_no_mains_gas",
              "flag_energy_zero_or_negative", "flag_no_heating_description", "flag_stale_epc"):
        d[f] = bool(d[f]) if d[f] is not None else False
    for f in ("sap_score", "age_end", "floor_area_m2", "multi_glaze_pct", "baseline_gas_kwh",
              "baseline_elec_kwh", "epc_age_years", "pv_roof_pct"):
        d[f] = _to_float(d[f])
    wt = _to_float(d["wind_turbines"])
    d["wind_turbines"] = None if wt is None or wt < 0 else int(wt)  # -1 = not recorded
    pc = _clean(row.get(POSTCODE_COLUMN))
    d["postcode_outward"] = pc.split()[0].upper() if isinstance(pc, str) and pc.strip() else None
    age = d.get("age_band") or "unknown age"
    ptype = (d.get("property_type") or "home").lower()
    d["display_label"] = f"{age} {ptype}, {d['postcode_outward'] or 'York'}"
    d["provenance"] = _provenance(d)
    return HomeRecord(**d)


def _provenance(d: dict) -> dict[str, Provenance]:
    def p(v, prov=Provenance.observed):
        return Provenance.unavailable if v is None else prov

    out = {
        "sap_score": p(d["sap_score"]),
        "floor_area_m2": p(d["floor_area_m2"]),
        "walls_rating": Provenance.not_applicable if d["walls_rating_status"] == "not_applicable" else p(d["walls_rating"]),
        "roof_rating": Provenance.not_applicable if d["roof_rating_status"] == "not_applicable" else p(d["roof_rating"]),
        "floor_rating": Provenance.not_applicable if d["floor_rating_status"] == "not_applicable" else p(d["floor_rating"]),
        "glazing": p(d["glazing"]),
        "heating_type": p(d["heating_type"]),
        "heating_rating": p(d["heating_rating"]),
        "controls": p(d["controls"]),
        "smart_controls": p(d["controls"], Provenance.assumption),  # D4: TTZC proxy
        "solar_pv": p(d["solar_pv"]),
    }
    for fuel in ("gas", "elec"):
        raw = d.get(f"prov_baseline_{fuel}_kwh")
        out[f"baseline_{fuel}_kwh"] = Provenance(raw) if raw in Provenance._value2member_map_ else p(d[f"baseline_{fuel}_kwh"])
    return out
