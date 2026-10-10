"""Full-state scenario IDs: same state -> same ID; any calculation change -> new ID."""

import math

import pytest

from scenario_id import canonical_json, scenario_id

STATE = {"property_id": "york-1", "measures": ["loft_insulation", "heat_pump"], "baseline": {"gas": 12000.0},
         "versions": {"catalogue": "cat-v1"}, "data_timestamp": "2026-10-10"}


def test_same_state_same_id_regardless_of_key_order():
    shuffled = {k: STATE[k] for k in reversed(list(STATE))}
    assert scenario_id(STATE) == scenario_id(shuffled)


def test_tiny_float_noise_does_not_change_id():
    noisy = {**STATE, "baseline": {"gas": 12000.0 + 1e-9}}
    assert scenario_id(noisy) == scenario_id(STATE)


@pytest.mark.parametrize("change", [
    {"measures": ["loft_insulation"]},
    {"baseline": {"gas": 12001.0}},
    {"versions": {"catalogue": "cat-v2"}},
])
def test_any_calculation_change_gives_new_id(change):
    assert scenario_id({**STATE, **change}) != scenario_id(STATE)


def test_timestamp_does_not_change_id():
    assert scenario_id({**STATE, "data_timestamp": "2027-01-01"}) == scenario_id(STATE)


def test_nan_is_rejected():
    with pytest.raises(ValueError):
        canonical_json({"x": math.nan})
