"""Feature contract (no label_only / restricted inputs), train/inference parity, frozen categories, after-state."""
import json
import math

import numpy as np
import pandas as pd
import pytest

from backend.app import config
from backend.app.ml import features as F
from backend.app.ml.privacy import is_restricted
from backend.app.schemas.enums import MeasureId as M
from tests.conftest import make_home, needs_data

ROLES = json.loads((config.CONFIGS / "feature_availability.json").read_text())["roles"]


def _cert_row(**kw):
    row = {"property_id": "P1", "c_rating": "D", "c_sap_score": 60, "c_property_type": "House",
           "c_built_form": "Semi-Detached", "c_age_band": "1950-1966", "c_age_start": 1950.0, "c_age_end": 1966.0,
           "c_floor_area_m2": 100.0, "c_walls_rating": "Average", "c_walls_rating_status": "observed",
           "walls_description": "Cavity wall, as built, no insulation (assumed)", "c_roof_rating": "Average",
           "c_roof_rating_status": "observed", "roof_description": "Pitched, 100 mm loft insulation",
           "c_floor_rating": None, "c_floor_rating_status": "not_applicable",
           "floor_description": "Suspended, no insulation (assumed)", "c_windows_rating": "Average",
           "c_glazing": "double", "c_multi_glaze_pct": 100.0, "c_heating_type": "gas_boiler",
           "c_heating_rating": "Good", "c_controls": "full", "c_solar_pv": False, "photo_supply": "0",
           "solar_water_heating_flag": "N", "wind_turbine_count": "0", "c_mains_gas": True,
           "main_fuel": "mains gas (not community)", "mainheat_description": "Boiler and radiators, mains gas",
           "number_habitable_rooms": "5", "transaction_type": "Marketed sale",
           "c_lodgement_date": pd.Timestamp("2019-03-01"), "postcode_outward": "YO31", "postcode_sector": "YO31 1"}
    row.update(kw)
    return row


# ---------------- (a) contract ----------------

def test_every_feature_has_a_documented_source():
    for purpose, cols in F.FEATURE_SETS.items():
        for c in cols:
            assert c in F.FEATURE_SOURCES, (purpose, c)


@pytest.mark.parametrize("purpose", list(F.FEATURE_SETS))
def test_no_label_only_or_restricted_source(purpose):
    for c in F.FEATURE_SETS[purpose]:
        for src in F.FEATURE_SOURCES[c]:
            if src in F.DESCRIPTION_SOURCES:
                continue   # certificate description text / lodgement date / derived outward code (plan §0.2)
            assert ROLES.get(src) == "feature_ok", (purpose, c, src, ROLES.get(src))
            assert not is_restricted(src)
        assert not c.startswith(("rec_", "potential_", "n_recommendations", "has_recommendations"))
    for src in F.DESCRIPTION_SOURCES:
        assert ROLES.get(src) not in ("label_only", "restricted_address")


def test_sap_features_exclude_the_target():
    assert not {"sap_score", "epc_band_ord"} & set(F.FEATURE_SETS["sap"])


def test_location_only_for_value():
    for purpose in ("sap", "recommender", "energy_york"):
        assert not {"postcode_district", "postcode_sector"} & set(F.FEATURE_SETS[purpose])


def test_monotone_vector_aligned():
    mc = F.monotone_constraints("sap")
    cols = F.FEATURE_SETS["sap"]
    assert len(mc) == len(cols)
    assert dict(zip(cols, mc))["walls_ord"] == 1 and dict(zip(cols, mc))["wall_u"] == -1
    assert dict(zip(cols, mc))["heating_family"] == 0 and dict(zip(cols, mc))["main_fuel"] == 0


# ---------------- (b) train / inference parity ----------------

def test_home_and_certificate_give_identical_features():
    row = _cert_row()
    home = make_home(walls_description=row["walls_description"], floor_description=row["floor_description"],
                     windows_rating="Average", main_fuel=row["main_fuel"],
                     mainheat_description=row["mainheat_description"], habitable_rooms=5.0,
                     transaction_type="Marketed sale", lodgement_date="2019-03-01", age_start=1950.0,
                     postcode_outward="YO31", postcode_sector="YO31 1")
    for purpose in F.FEATURE_SETS:
        a = F.features(F.state_from_home(home), purpose)
        b = F.features(F.state_from_certificate(row), purpose)
        assert a.keys() == b.keys()
        for k in a:
            assert a[k] == b[k] or (isinstance(a[k], float) and math.isnan(a[k]) and math.isnan(b[k])), (purpose, k)


def test_frames_have_identical_columns_and_dtypes():
    st = F.state_from_certificate(_cert_row())
    train = pd.DataFrame([F.features(st, "sap"), F.features(F.state_from_certificate(_cert_row(c_glazing="single")), "sap")])
    cats = F.fit_categories(train, F.FEATURE_SETS["sap"])
    x1 = F.to_frame(train, F.FEATURE_SETS["sap"], cats)
    x2 = F.to_frame([F.features(st, "sap")], F.FEATURE_SETS["sap"], cats)
    assert list(x1.columns) == list(x2.columns) == list(F.FEATURE_SETS["sap"])
    assert (x1.dtypes == x2.dtypes).all()


# ---------------- (c) frozen categories ----------------

def test_unseen_category_maps_to_missing_and_levels_are_sorted():
    train = pd.DataFrame({"wall_type": ["solid", "cavity", None], "log_floor_area": [1.0, 2.0, 3.0]})
    cats = F.fit_categories(train, ["wall_type", "log_floor_area"])
    assert cats == {"wall_type": ["cavity", "solid"]}
    x = F.to_frame(pd.DataFrame({"wall_type": ["timber", "solid"], "log_floor_area": [1.5, None]}),
                   ["wall_type", "log_floor_area"], cats)
    assert pd.isna(x.wall_type.iloc[0]) and x.wall_type.iloc[1] == "solid"
    assert list(x.wall_type.cat.categories) == ["cavity", "solid"] and np.isnan(x.log_floor_area.iloc[1])


# ---------------- derivation details ----------------

def test_ratings_na_and_missing_flags():
    d = F.derive(F.state_from_certificate(_cert_row(c_walls_rating=None, c_walls_rating_status="observed")))
    assert math.isnan(d["walls_ord"]) and d["walls_missing"] == 1 and d["walls_na"] == 0
    assert d["floor_ord"] == 0 and d["floor_na"] == 1
    assert d["roof_ord"] == 3 and d["loft_mm"] == 100


def test_missing_is_nan_never_zero():
    d = F.derive(F.state_from_certificate(_cert_row(c_floor_area_m2=None, number_habitable_rooms=None,
                                                    c_solar_pv=None, photo_supply=None, c_glazing=None,
                                                    c_multi_glaze_pct=None)))
    for k in ("log_floor_area", "habitable_rooms", "area_per_room", "solar_pv", "pv_roof_pct", "glazing_ord",
              "multi_glaze_pct"):
        assert math.isnan(d[k]), k


def test_lodgement_year_override_and_glazing_imputation():
    st = F.state_from_certificate(_cert_row(c_glazing="partial", c_multi_glaze_pct=None))
    d = F.derive(st, lodgement_year=2026)
    assert d["lodgement_year"] == 2026 and F.derive(st)["lodgement_year"] == 2019
    assert d["multi_glaze_pct"] == 50.0 and d["multi_glaze_pct_missing"] == 1


def test_sale_features():
    s = F.sale_features(1, "L", "Flat/Maisonette", "2026-03-15")
    assert s == {"new_build": 1.0, "tenure_leasehold": 1.0, "lr_type": "Flat/Maisonette", "sale_month_index": 14.0}


# ---------------- after-retrofit features ----------------

def test_after_features_only_improve_monotone_inputs():
    home = make_home(walls_rating="Poor", roof_rating="Poor", glazing="partial", multi_glaze_pct=40.0,
                     controls="timer", solar_pv=False)
    before = F.features(F.state_from_home(home), "sap", 2026)
    after = F.after_features(home, list(M), "sap", 2026)
    for c in F.SAP_MONOTONE_UP:
        if not math.isnan(before[c]):
            assert after[c] >= before[c], c
    assert after["walls_ord"] == 4 and after["roof_ord"] == 4 and after["glazing_ord"] == 2
    assert after["controls_ord"] == 3 and after["solar_pv"] == 1 and after["loft_mm"] == 270
    assert after["wall_ins_level"] == 2 and after["heating_family"] == "heat_pump"


def test_after_features_never_turn_missing_into_known():
    home = make_home(roof_description="Pitched, insulated (assumed)", walls_description="SAP05:Walls", controls=None)
    after = F.after_features(home, [M.loft_insulation, M.cavity_wall, M.smart_thermostat], "sap", 2026)
    assert math.isnan(after["loft_mm"]) and math.isnan(after["wall_ins_level"]) and math.isnan(after["controls_ord"])


# ---------------- real data round trip ----------------

@needs_data
def test_round_trip_real_homes_against_latest_certificate():
    from backend.app.data.loaders import homes_frame
    from backend.app.ml.privacy import safe_read_parquet
    from backend.app.schemas.property import home_from_row

    hf = homes_frame()
    ids = hf.property_id.sort_values().iloc[::997].tolist()[:60]
    certs = safe_read_parquet(config.REGION_DIR / "epc_certs_all.parquet", columns=[*F.CERT_COLUMNS, "certificate_number"],
                              derive_postcode=True)
    latest = dict(zip(hf.property_id, pd.read_parquet(config.HOMES_TAGGED, columns=["certificate_number"]).certificate_number))
    by_cert = certs.set_index("certificate_number")
    for pid in ids:
        row = by_cert.loc[latest[pid]].to_dict()
        row["property_id"] = pid
        a = F.derive(F.state_from_home(home_from_row(hf.loc[pid].to_dict())))
        b = F.derive(F.state_from_certificate(row))
        for k in a:
            assert a[k] == b[k] or (isinstance(a[k], float) and math.isnan(a[k]) and math.isnan(b[k])), (pid, k)
