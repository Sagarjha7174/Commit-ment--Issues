"""Rendering: units, rounding, signs and unavailable values."""

from backend.app.llm.facts_view import Fact
from backend.app.llm.render import format_fact, placeholders


def f(kind, value, status="available"):
    return Fact("k", value, kind, "label", status)


def test_kwh_rounding_and_units():
    assert format_fact(f("kwh_change", 11400.0)) == "11,400 kWh/year"
    assert format_fact(f("kwh_change", 1832.7)) == "1,830 kWh/year"
    assert format_fact(f("kwh_change", 360.4)) == "360 kWh/year"


def test_abs_filter_turns_increase_into_magnitude():
    assert format_fact(f("kwh_change", -1832.7), use_abs=True) == "1,830 kWh/year"
    assert format_fact(f("kwh_change", -1832.7)) == "1,830 kWh/year"  # direction comes from the wording


def test_carbon_switches_to_tonnes():
    assert format_fact(f("kg_change", 1814.5)) == "1.8 tonnes CO2e/year"
    assert format_fact(f("kg_change", 279.8)) == "280 kg CO2e/year"


def test_money_percent_score():
    assert format_fact(f("gbp", 20500.0)) == "£20,500"
    assert format_fact(f("pct", 56.9)) == "57%"
    assert format_fact(f("pct", 4.0)) == "4.0%"
    assert format_fact(f("score", 38)) == "38/100"
    assert format_fact(f("score_range", (43, 58))) == "43–58"


def test_unavailable_is_never_zero():
    assert format_fact(f("kwh_change", None, "unavailable")) == "not available"
    assert format_fact(f("gbp_change", None, "not_estimated")) == "not estimated"
    assert format_fact(f("kwh", 0.0)) == "0 kWh/year"  # a real zero stays a zero


def test_text_list_joins_naturally():
    assert format_fact(f("text_list", ["a", "b", "c"])) == "a, b and c"
    assert format_fact(f("text_list", ["a"])) == "a"


def test_placeholder_parsing():
    assert placeholders("x {a.b.0.c} y {d_e|abs}") == [("a.b.0.c", False), ("d_e", True)]


def test_change_filters_carry_direction():
    from backend.app.llm.render import format_change
    assert format_change(f("kwh_change", 11400.0), False) == "fall by 11,400 kWh/year"
    assert format_change(f("kwh_change", -1832.7), True) == "rises by 1,830 kWh/year"
    assert format_change(f("kwh_change", 0.0), True) == "does not change"
    assert format_change(f("gbp_change", 2500.0), False) == "go up by £2,500"
