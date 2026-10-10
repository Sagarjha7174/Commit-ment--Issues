"""Shared ML feature layer: one code path for training and inference. Pure functions, no I/O.

state_from_home(HomeRecord) and state_from_certificate(row) return the same dict of HomeRecord field names, so homes,
historical certificates and sales all go through features(state, purpose). Only feature_ok columns and certificate
description text are read (FEATURE_SOURCES; tested against configs/feature_availability.json). Missing stays NaN plus
a *_missing flag, never 0.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from ..schemas.enums import MeasureId
from ..schemas.property import HomeRecord, home_from_row
from . import parsers as P

FEATURES_VERSION = "ml-features-v1"

STATE_FIELDS = (
    "rating", "sap_score", "property_type", "built_form", "age_band", "age_start", "age_end", "floor_area_m2",
    "walls_rating", "walls_rating_status", "walls_description", "roof_rating", "roof_rating_status", "roof_description",
    "floor_rating", "floor_rating_status", "floor_description", "windows_rating", "glazing", "multi_glaze_pct",
    "heating_type", "heating_rating", "controls", "solar_pv", "pv_roof_pct", "solar_water_heating", "wind_turbines",
    "mains_gas", "main_fuel", "mainheat_description", "habitable_rooms", "transaction_type", "lodgement_date",
    "postcode_outward", "postcode_sector",
)

# epc_certs_all column -> homes_tagged column, so a certificate goes through the same home_from_row conversion
CERT_TO_TAGGED = {
    "property_id": "property_id", "c_rating": "rating", "c_sap_score": "sap_score", "c_property_type": "property_type",
    "c_built_form": "built_form", "c_age_band": "age_band", "c_age_start": "age_start", "c_age_end": "age_end",
    "c_floor_area_m2": "floor_area_m2", "c_walls_rating": "walls_rating", "c_walls_rating_status": "walls_rating_status",
    "walls_description": "raw_walls_description", "c_roof_rating": "roof_rating",
    "c_roof_rating_status": "roof_rating_status", "roof_description": "raw_roof_description",
    "c_floor_rating": "floor_rating", "c_floor_rating_status": "floor_rating_status",
    "floor_description": "raw_floor_description", "c_windows_rating": "windows_rating", "c_glazing": "glazing",
    "c_multi_glaze_pct": "multi_glaze_pct", "c_heating_type": "heating_type", "c_heating_rating": "heating_rating",
    "c_controls": "controls", "c_solar_pv": "solar_pv", "photo_supply": "raw_photo_supply",
    "solar_water_heating_flag": "raw_solar_water_heating_flag", "wind_turbine_count": "raw_wind_turbine_count",
    "c_mains_gas": "mains_gas", "main_fuel": "raw_main_fuel", "mainheat_description": "raw_mainheat_description",
    "number_habitable_rooms": "raw_number_habitable_rooms", "transaction_type": "raw_transaction_type",
    "c_lodgement_date": "lodgement_date",
}
CERT_COLUMNS = tuple(CERT_TO_TAGGED)

RATING = {"Very Poor": 1, "Poor": 2, "Average": 3, "Good": 4, "Very Good": 5}
GLAZING = {"single": 0, "partial": 1, "double": 2, "triple": 3}
CONTROLS = {"none": 0, "timer": 1, "full": 2, "smart": 3}
EPC_BAND = {"A": 7, "B": 6, "C": 5, "D": 4, "E": 3, "F": 2, "G": 1}
NEED_EPC = {"A": "A/B", "B": "A/B", "C": "C", "D": "D", "E": "E", "F": "F/G", "G": "F/G"}
NEED_TYPE = {"Semi-Detached": "Semi detached", "Mid-Terrace": "Mid terrace", "Detached": "Detached",
             "End-Terrace": "End terrace", "Enclosed Mid-Terrace": "Mid terrace", "Enclosed End-Terrace": "End terrace"}
ELEMENTS = ("walls", "roof", "floor", "windows", "heating")
PARTIAL_GLAZING_MISSING_PCT = 50.0   # same assumption as the score (score_mappings windows.partial_missing_pct)
LOFT_AFTER_MM = 270                  # engine_params.loft.already_sufficient_mm: an insulated loft


# ---------------- canonical state ----------------

def state_from_home(home: HomeRecord) -> dict:
    return {f: getattr(home, f) for f in STATE_FIELDS}


def state_from_certificate(row: dict) -> dict:
    """Canonical state of one certificate row (epc_certs_all columns; postcode_outward/sector already derived)."""
    tagged = {CERT_TO_TAGGED[k]: v for k, v in row.items() if k in CERT_TO_TAGGED}
    tagged["property_id"] = str(row.get("property_id") or "cert")
    st = state_from_home(home_from_row(tagged))
    st["postcode_outward"] = _none(row.get("postcode_outward"))
    st["postcode_sector"] = _none(row.get("postcode_sector"))
    return st


def _none(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if v is pd.NA or v is pd.NaT:
        return None
    return v


def _f(v) -> float:
    v = _none(v)
    return float("nan") if v is None else float(v)


def _year(d) -> Optional[int]:
    d = _none(d)
    if d is None:
        return None
    try:
        return int(str(d)[:4])
    except ValueError:
        return None


# ---------------- derivation ----------------

def derive(state: dict, lodgement_year: Optional[int] = None) -> dict:
    """Every feature for one state (superset of all purposes). lodgement_year overrides the certificate's year
    (inference: the model's reference year, so ΔSAP compares two states under one methodology)."""
    s = state
    f: dict = {}
    for el in ELEMENTS:
        r = s.get(f"{el}_rating")
        status = s.get(f"{el}_rating_status")
        if status == "not_applicable":
            f[f"{el}_ord"], f[f"{el}_na"], f[f"{el}_missing"] = 0.0, 1.0, 0.0
        elif r in RATING:
            f[f"{el}_ord"], f[f"{el}_na"], f[f"{el}_missing"] = float(RATING[r]), 0.0, 0.0
        else:
            f[f"{el}_ord"], f[f"{el}_na"], f[f"{el}_missing"] = np.nan, 0.0, 1.0

    g = s.get("glazing")
    f["glazing_ord"] = float(GLAZING[g]) if g in GLAZING else np.nan
    pct = _f(s.get("multi_glaze_pct"))
    f["multi_glaze_pct_missing"] = 1.0 if math.isnan(pct) else 0.0
    if math.isnan(pct):   # consistent with the glazing state; partial and unknown share = score assumption (50%)
        pct = {"single": 0.0, "double": 100.0, "triple": 100.0, "partial": PARTIAL_GLAZING_MISSING_PCT}.get(g, np.nan)
    f["multi_glaze_pct"] = float(min(max(pct, 0.0), 100.0)) if not math.isnan(pct) else np.nan
    c = s.get("controls")
    f["controls_ord"] = float(CONTROLS[c]) if c in CONTROLS else np.nan
    pv = _none(s.get("solar_pv"))
    f["solar_pv"] = np.nan if pv is None else float(bool(pv))
    roof_pct = _f(s.get("pv_roof_pct"))
    if math.isnan(roof_pct) and pv is False:
        roof_pct = 0.0    # no PV recorded -> 0% of roof
    f["pv_roof_pct"] = roof_pct
    sw = _none(s.get("solar_water_heating"))
    f["solar_water_heating"] = np.nan if sw is None else float(bool(sw))

    lm = P.loft_mm(s.get("roof_description"))
    f["loft_mm"] = np.nan if lm is None else float(min(lm, 400))
    f["wall_type"] = P.wall_type(s.get("walls_description"))
    wl = P.wall_insulation_level(s.get("walls_description"))
    f["wall_ins_level"] = np.nan if wl is None else float(wl)
    f["wall_u"] = _f(P.u_value(s.get("walls_description")))
    f["roof_type"] = P.roof_type(s.get("roof_description"))
    f["roof_u"] = _f(P.u_value(s.get("roof_description")))
    f["floor_type"] = P.floor_type(s.get("floor_description"))
    fl = P.floor_insulation_level(s.get("floor_description"))
    f["floor_ins_level"] = np.nan if fl is None else float(fl)
    f["floor_u"] = _f(P.u_value(s.get("floor_description")))
    f["main_fuel"] = P.main_fuel(s.get("main_fuel"))
    f["heating_family"] = P.heating_family(s.get("mainheat_description"))

    area = _f(s.get("floor_area_m2"))
    area = area if (not math.isnan(area) and 15 <= area <= 1000) else np.nan
    f["log_floor_area"] = math.log(area) if not math.isnan(area) else np.nan
    rooms = _f(s.get("habitable_rooms"))
    rooms = rooms if (not math.isnan(rooms) and 1 <= rooms <= 30) else np.nan
    f["habitable_rooms"] = rooms
    f["area_per_room"] = area / rooms if not (math.isnan(area) or math.isnan(rooms)) else np.nan
    f["age_mid_year"] = _f(P.age_mid_year(s.get("age_band"), _none(s.get("age_start")), _none(s.get("age_end"))))
    pt, bf = s.get("property_type"), s.get("built_form")
    f["property_type"] = pt
    f["built_form"] = bf
    f["type_form"] = f"{pt}|{bf or 'unknown'}" if pt else None
    mg = _none(s.get("mains_gas"))
    f["mains_gas"] = np.nan if mg is None else float(bool(mg))
    yr = lodgement_year if lodgement_year is not None else _year(s.get("lodgement_date"))
    f["lodgement_year"] = np.nan if yr is None else float(yr)
    f["transaction_type"] = P.transaction_type(s.get("transaction_type"))
    f["postcode_district"] = _none(s.get("postcode_outward"))
    f["postcode_sector"] = _none(s.get("postcode_sector"))
    f["sap_score"] = _f(s.get("sap_score"))
    f["epc_band_ord"] = float(EPC_BAND[s["rating"]]) if s.get("rating") in EPC_BAND else np.nan

    # NEED-coded features (energy model trained on NEED, applied to York homes)
    if pt in ("Flat", "Maisonette"):
        need_type = "Flat"
    elif pt == "Bungalow":
        need_type = "Bungalow"
    elif pt == "House":
        need_type = NEED_TYPE.get(bf or "")
    else:
        need_type = None
    f["need_property_type"] = need_type
    f["need_age_band"] = _f(P.need_age_band(_none(s.get("age_end"))))
    from ..services.baseline import area_band
    ab = area_band(None if math.isnan(area) else area)
    f["need_floor_area_band"] = np.nan if ab is None else float(ab)
    f["need_epc_band"] = NEED_EPC.get(s.get("rating") or "")
    fuel = f["main_fuel"]
    f["need_main_heat_gas"] = np.nan if fuel is None else float(fuel == "mains_gas")
    f["need_region"] = "E12000003"   # every York home: Yorkshire and The Humber
    return f


# ---------------- feature sets (the contract) ----------------

SAP_MONOTONE_UP = ("walls_ord", "roof_ord", "floor_ord", "windows_ord", "heating_ord", "glazing_ord", "multi_glaze_pct",
                   "controls_ord", "solar_pv", "pv_roof_pct", "loft_mm", "wall_ins_level", "floor_ins_level",
                   "solar_water_heating")
SAP_MONOTONE_DOWN = ("wall_u", "roof_u", "floor_u")   # lower U-value = better fabric
_STATE_CORE = (*SAP_MONOTONE_UP, *SAP_MONOTONE_DOWN,
               "walls_na", "roof_na", "floor_na", "windows_na", "walls_missing", "roof_missing", "floor_missing",
               "windows_missing", "heating_missing", "multi_glaze_pct_missing",
               "wall_type", "roof_type", "floor_type", "main_fuel", "heating_family",
               "log_floor_area", "habitable_rooms", "area_per_room", "age_mid_year", "type_form", "mains_gas")

FEATURE_SETS: dict[str, tuple[str, ...]] = {
    # SAP model: the home's recorded state -> SAP. No rating / sap_score (the target in another form).
    "sap": (*_STATE_CORE, "lodgement_year", "transaction_type"),
    # value model (state part; sale fields come from sale_features). Element ratings are left out so the SAP score
    # carries the energy-efficiency signal (D33).
    "value": ("sap_score", "log_floor_area", "habitable_rooms", "area_per_room", "age_mid_year", "property_type",
              "built_form", "type_form", "wall_type", "roof_type", "floor_type", "heating_family", "main_fuel",
              "mains_gas", "glazing_ord", "solar_pv", "postcode_district", "postcode_sector"),
    # energy model: only fields NEED and York homes share (plan M4)
    "energy_york": ("need_property_type", "need_age_band", "need_floor_area_band", "need_epc_band",
                    "need_main_heat_gas", "solar_pv", "need_region"),
    # recommender: the certificate state + its SAP and year (assessor software version)
    "recommender": (*_STATE_CORE, "sap_score", "epc_band_ord", "lodgement_year", "transaction_type"),
}
SALE_FEATURES = ("new_build", "tenure_leasehold", "lr_type", "sale_month_index")
CATEGORICAL = frozenset({"wall_type", "roof_type", "floor_type", "main_fuel", "heating_family", "property_type",
                         "built_form", "type_form", "transaction_type", "postcode_district", "postcode_sector",
                         "need_property_type", "need_epc_band", "need_region", "lr_type"})

# where each feature comes from (homes_tagged column names; checked against feature_availability.json roles)
DESCRIPTION_SOURCES = frozenset({"raw_walls_description", "raw_roof_description", "raw_floor_description",
                                 "raw_main_fuel", "raw_mainheat_description", "raw_transaction_type",
                                 "raw_number_habitable_rooms", "raw_photo_supply", "raw_solar_water_heating_flag",
                                 "lodgement_date", "postcode(outward/sector only)"})
FEATURE_SOURCES: dict[str, tuple[str, ...]] = {
    **{f"{el}_{k}": (f"{el}_rating",) for el in ("walls", "roof", "floor", "windows") for k in ("ord", "na", "missing")},
    "heating_ord": ("heating_rating",), "heating_na": ("heating_rating",), "heating_missing": ("heating_rating",),
    "glazing_ord": ("glazing",), "multi_glaze_pct": ("multi_glaze_pct", "glazing"),
    "multi_glaze_pct_missing": ("multi_glaze_pct",), "controls_ord": ("controls",), "solar_pv": ("solar_pv",),
    "pv_roof_pct": ("raw_photo_supply", "solar_pv"), "solar_water_heating": ("raw_solar_water_heating_flag",),
    "loft_mm": ("raw_roof_description",), "wall_type": ("raw_walls_description",),
    "wall_ins_level": ("raw_walls_description",), "wall_u": ("raw_walls_description",),
    "roof_type": ("raw_roof_description",), "roof_u": ("raw_roof_description",),
    "floor_type": ("raw_floor_description",), "floor_ins_level": ("raw_floor_description",),
    "floor_u": ("raw_floor_description",), "main_fuel": ("raw_main_fuel",),
    "heating_family": ("raw_mainheat_description",), "log_floor_area": ("floor_area_m2",),
    "habitable_rooms": ("raw_number_habitable_rooms",), "area_per_room": ("floor_area_m2", "raw_number_habitable_rooms"),
    "age_mid_year": ("age_band", "age_start", "age_end"), "property_type": ("property_type",),
    "built_form": ("built_form",), "type_form": ("property_type", "built_form"), "mains_gas": ("mains_gas",),
    "lodgement_year": ("lodgement_date",), "transaction_type": ("raw_transaction_type",),
    "postcode_district": ("postcode(outward/sector only)",), "postcode_sector": ("postcode(outward/sector only)",),
    "sap_score": ("sap_score",), "epc_band_ord": ("rating",),
    "need_property_type": ("property_type", "built_form"), "need_age_band": ("age_end",),
    "need_floor_area_band": ("floor_area_m2",), "need_epc_band": ("rating",), "need_main_heat_gas": ("raw_main_fuel",),
    "need_region": (),
}


def monotone_constraints(purpose: str) -> list[int]:
    if purpose != "sap":
        return [0] * len(FEATURE_SETS[purpose])
    return [1 if c in SAP_MONOTONE_UP else -1 if c in SAP_MONOTONE_DOWN else 0 for c in FEATURE_SETS[purpose]]


def features(state: dict, purpose: str, lodgement_year: Optional[int] = None) -> dict:
    d = derive(state, lodgement_year)
    return {c: d[c] for c in FEATURE_SETS[purpose]}


def sale_features(new_build, tenure, lr_type, sale_date) -> dict:
    """Sale fields (Land Registry): new build 0/1, leasehold 0/1, LR type label, months since 2025-01."""
    d = pd.Timestamp(sale_date) if _none(sale_date) is not None else None
    return {"new_build": _f(new_build), "tenure_leasehold": np.nan if _none(tenure) is None else float(tenure == "L"),
            "lr_type": _none(lr_type),
            "sale_month_index": np.nan if d is None else float((d.year - 2025) * 12 + d.month - 1)}


# ---------------- after-retrofit state ----------------

def after_features(home: HomeRecord, measures: Iterable[MeasureId], purpose: str,
                   lodgement_year: Optional[int] = None) -> dict:
    """Features of the home after the measures: score.apply_state_effects (ratings, glazing, controls, heating, PV),
    plus the description-derived features each measure changes. Only known values are raised, so every monotone
    feature moves from one known value to a better one (never from missing to known)."""
    from ..services.score import apply_state_effects
    ms = list(measures)
    after = apply_state_effects(home, ms)
    d = derive(state_from_home(after), lodgement_year)
    if MeasureId.loft_insulation in ms and not math.isnan(d["loft_mm"]) and d["roof_type"] == "pitched":
        d["loft_mm"] = max(d["loft_mm"], float(LOFT_AFTER_MM))
    if (MeasureId.cavity_wall in ms or MeasureId.solid_wall in ms) and not math.isnan(d["wall_ins_level"]):
        d["wall_ins_level"] = max(d["wall_ins_level"], 2.0)
    if MeasureId.solar_pv in ms and math.isnan(d["pv_roof_pct"]):
        # new PV of unknown size (state effects: pv_roof_pct_if_unknown = null): keep the recorded share (0), so only
        # the PV flag is credited; conservative, never a missing value
        d["pv_roof_pct"] = derive(state_from_home(home), lodgement_year)["pv_roof_pct"]
    if MeasureId.heat_pump in ms and after.heating_type == "heat_pump":
        d["heating_family"] = "heat_pump"
        if d["main_fuel"] is not None:
            d["main_fuel"] = "electricity"
    return {c: d[c] for c in FEATURE_SETS[purpose]}


# ---------------- frames with frozen categories ----------------

def fit_categories(frame: pd.DataFrame, purpose_cols: Iterable[str]) -> dict[str, list[str]]:
    """Category levels from TRAIN rows only (sorted for determinism); stored in meta.json."""
    return {c: sorted(str(v) for v in frame[c].dropna().unique()) for c in purpose_cols if c in CATEGORICAL}


def to_frame(rows: list[dict] | pd.DataFrame, columns: Iterable[str], categories: dict[str, list[str]]) -> pd.DataFrame:
    """Model matrix in a fixed column order: numerics float64, categoricals with the frozen train levels
    (an unseen level becomes missing)."""
    cols = list(columns)
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows, columns=cols)
    out = {}
    for c in cols:
        if c in CATEGORICAL:
            levels = categories.get(c, [])
            known = set(levels)
            vals = [None if (v is None or (isinstance(v, float) and math.isnan(v)) or str(v) not in known) else str(v)
                    for v in df[c].astype(object).tolist()]
            out[c] = pd.Categorical(vals, categories=levels)
        else:
            out[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    return pd.DataFrame(out, columns=cols, index=df.index)
