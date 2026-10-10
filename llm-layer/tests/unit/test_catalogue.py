import json
from pathlib import Path

import pytest

CAT = Path(__file__).resolve().parents[2] / "configs" / "retrofit_catalogue.json"
MEASURES = {"loft_insulation", "cavity_wall", "solid_wall", "double_glazing", "smart_thermostat", "heat_pump", "solar_pv"}
NEED_BASED = {"loft_insulation", "cavity_wall", "solid_wall", "solar_pv"}
BASES = {"total_gas", "space_heat_demand", "total_grid_electricity"}


@pytest.fixture(scope="module")
def cat():
    return json.loads(CAT.read_text())


def test_loads_and_versions_match(cat):
    assert cat["version"] == "cat-v3"
    assert all(m["version"] == cat["version"] for m in cat["measures"])


def test_all_seven_present(cat):
    assert {m["id"] for m in cat["measures"]} == MEASURES
    assert len(cat["measures"]) == 7


def test_every_entry_has_basis_and_source(cat):
    for m in cat["measures"]:
        assert m["impact_basis"] in BASES, m["id"]
        assert m["source"], m["id"]
        assert m["target_end_use"], m["id"]
        assert "applicability_rules" in m and m["applicability_rules"]["text"]


def test_no_measured_pct_without_basis(cat):
    for m in cat["measures"]:
        pct_keys = [k for k in m["impact"] if k in ("low", "mid", "high")]
        if pct_keys:
            assert m["impact_basis"] in BASES
            assert 0 < m["impact"]["low"] <= m["impact"]["mid"] <= m["impact"]["high"] < 1, m["id"]


def test_validated_flags(cat):
    for m in cat["measures"]:
        assert m["validated"] is (m["id"] in NEED_BASED), m["id"]
        if m["id"] in NEED_BASED:
            assert "Impact_of_measures" in m["source_table"]


def test_need_headline_values(cat):
    mid = {m["id"]: m["impact"].get("mid") for m in cat["measures"]}
    assert round(mid["solid_wall"], 3) == 0.173
    assert round(mid["cavity_wall"], 3) == 0.120
    assert round(mid["loft_insulation"], 3) == 0.032
    assert round(mid["solar_pv"], 3) == 0.122


def test_heat_pump_and_globals(cat):
    hp = next(m for m in cat["measures"] if m["id"] == "heat_pump")
    assert hp["impact"]["scop_mid"] == 3.0 and hp["impact"]["scop_low"] == 2.5 and hp["impact"]["scop_high"] == 3.5
    assert set(hp["dependencies"]) >= {"loft_insulation", "cavity_wall", "solid_wall"}
    g = cat["global"]
    for k in ("boiler_efficiency", "space_share_of_heat_water_gas", "water_share_of_heat_water_gas"):
        assert g[k]["status"] == "assumption"
    assert g["space_share_of_heat_water_gas"]["value"] == 0.77  # D11
    assert abs(g["space_share_of_heat_water_gas"]["value"] + g["water_share_of_heat_water_gas"]["value"] - 1) < 1e-9
    o = g["other_gas_share"]
    assert 0 < o["value"] < 0.1 and o["source"] and o["status"] == "published_national_average"
    assert "space_share" not in g  # ambiguous cat-v1 key removed


def test_costs_have_status(cat):
    for m in cat["measures"]:
        c = m["cost"]
        assert c["status"] in {"derived_from_data", "derived_from_data_low_confidence", "assumption", "unavailable"}
        if c["status"] == "unavailable":
            assert c["mid"] is None
        else:
            assert c["low"] <= c["mid"] <= c["high"] and c["source"]


def test_heat_pump_scop_global(cat):
    s = cat["global"]["heat_pump_scop"]
    assert (s["low"], s["mid"], s["high"]) == (2.5, 3.0, 3.5) and s["status"] == "assumption"
