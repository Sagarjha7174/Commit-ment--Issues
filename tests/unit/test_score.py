import pytest

from backend.app import config
from backend.app.schemas.enums import MeasureId, ValueStatus
from backend.app.services import score as S
from tests.conftest import DEMO_A, DEMO_C, make_home, needs_data

RATINGS = ["Very Poor", "Poor", "Average", "Good", "Very Good"]


def test_weights_sum_to_one_and_fixed():
    w = config.score_mappings()["weights"]
    assert abs(sum(w.values()) - 1) < 1e-12
    assert w == {"energy_efficiency": 0.25, "energy_intensity": 0.20, "insulation": 0.15, "heating": 0.15,
                 "windows": 0.10, "renewables": 0.10, "smart_controls": 0.05}


def test_params_read_from_config_not_recomputed():
    p = config.score_params()["intensity"]
    assert (p["p10"], p["p90"]) == (75.749, 186.022)
    assert S.sub_from_intensity(75.749) == 100 and S.sub_from_intensity(186.022) == 0


@pytest.mark.parametrize("total,label", [(29, "Very poor"), (30, "Poor"), (49, "Poor"), (50, "Moderate"),
                                         (64, "Moderate"), (65, "Good"), (79, "Good"), (80, "Highly efficient"),
                                         (0, "Very poor"), (100, "Highly efficient")])
def test_class_boundaries(total, label):
    assert S.classify(total) == label


@pytest.mark.parametrize("x,r", [(29.5, 30), (29.49, 29), (49.5, 50), (64.5, 65), (79.5, 80), (0.4, 0)])
def test_round_half_up(x, r):
    assert S.round_half_up(x) == r


def test_total_in_range_extremes():
    best = make_home(sap_score=120, baseline_gas_kwh=0.0, baseline_elec_kwh=1000.0, walls_rating="Very Good",
                     roof_rating="Very Good", heating_type="heat_pump", heating_rating="Very Good", glazing="triple",
                     solar_pv=True, pv_roof_pct=80.0, controls="smart")
    worst = make_home(sap_score=1, baseline_gas_kwh=40000.0, walls_rating="Very Poor", roof_rating="Very Poor",
                      heating_rating="Very Poor", glazing="single", controls="none")
    b, w = S.score_home(best), S.score_home(worst)
    assert b.total == 100 and b.classification == "Highly efficient"
    assert 0 <= w.total <= 29 and w.classification == "Very poor"


# ---- monotonicity: a better state never gives a lower sub-score ----

def test_monotone_energy_efficiency():
    subs = [S.sub_energy_efficiency(make_home(sap_score=s))[0] for s in range(-5, 130, 5)]
    assert subs == sorted(subs)


def test_monotone_intensity():
    subs = [S.sub_energy_intensity(make_home(), g, 3000.0, None)[0] for g in range(30000, -1, -1000)]
    assert subs == sorted(subs)


@pytest.mark.parametrize("el", ["walls_rating", "roof_rating"])
def test_monotone_insulation(el):
    subs = [S.sub_insulation(make_home(**{el: r}))[0] for r in RATINGS]
    assert subs == sorted(subs) and len(set(subs)) == 5


def test_monotone_heating_and_heat_pump_floor():
    subs = [S.sub_heating(make_home(heating_rating=r))[0] for r in RATINGS]
    assert subs == sorted(subs)
    hp = [S.sub_heating(make_home(heating_type="heat_pump", heating_rating=r))[0] for r in RATINGS]
    assert hp == sorted(hp) and min(hp) == 75
    assert all(h >= s for h, s in zip(hp, subs))


def test_monotone_windows():
    seq = [make_home(glazing="single")] + [make_home(glazing="partial", multi_glaze_pct=p) for p in (0, 25, 50, 99, 100)] \
        + [make_home(glazing="double"), make_home(glazing="triple")]
    subs = [S.sub_windows(h)[0] for h in seq]
    assert subs == sorted(subs)
    assert subs[0] == 10 and subs[-2] == 75 and subs[-1] == 100


def test_monotone_renewables():
    seq = [make_home(solar_pv=False), make_home(solar_pv=True, pv_roof_pct=20.0), make_home(solar_pv=True, pv_roof_pct=50.0),
           make_home(solar_pv=True, pv_roof_pct=50.0, solar_water_heating=True)]
    subs = [S.sub_renewables(h)[0] for h in seq]
    assert subs == [0, 60, 100, 100]
    assert S.sub_renewables(make_home(solar_pv=False, solar_water_heating=True))[0] == 30


def test_monotone_controls():
    subs = [S.sub_smart_controls(make_home(controls=c))[0] for c in ("none", "timer", "full", "smart")]
    assert subs == [0, 40, 70, 100]


def test_not_applicable_elements_skipped_not_penalised():
    flat = make_home(roof_rating=None, roof_rating_status="not_applicable", walls_rating="Good")
    assert S.sub_insulation(flat)[0] == 80


# ---- missing parts ----

def test_missing_part_headline_range_and_completeness():
    h = make_home(glazing=None)
    s = S.score_home(h)
    full = S.score_home(make_home())
    assert s.status == ValueStatus.ok and s.completeness == "6/7" and s.missing_parts == ["windows"]
    win = next(p for p in s.parts if p.part == "windows")
    assert win.sub is None and win.used_sub == 50 and win.status == "missing"
    others = sum(p.points for p in s.parts if p.part != "windows")
    assert s.range_low == S.round_half_up(others) and s.range_high == S.round_half_up(others + 10)
    assert s.range_low <= s.total <= s.range_high
    assert full.completeness == "7/7" and full.range_low == full.range_high == full.total


def test_two_missing_ok_three_missing_unavailable():
    two = S.score_home(make_home(glazing=None, controls=None))
    three = S.score_home(make_home(glazing=None, controls=None, solar_pv=None))
    assert two.status == ValueStatus.ok and two.total is not None
    assert three.status == ValueStatus.unavailable and three.total is None and three.classification is None
    assert three.completeness == "4/7"


def test_missing_baseline_is_not_zero():
    s = S.score_home(make_home(baseline_gas_kwh=None, gas_status="unknown_mains_gas"))
    p = next(p for p in s.parts if p.part == "energy_intensity")
    assert p.sub is None and "energy_intensity" in s.missing_parts


def test_conflict_flag_makes_intensity_missing():
    s = S.score_home(make_home(flag_conflict_gas_heating_no_mains_gas=True))
    assert "energy_intensity" in s.missing_parts


def test_key_issues_are_parts_below_50():
    s = S.score_home(make_home(glazing="single"))
    assert any(i.startswith("windows") for i in s.key_issues)
    assert all(p.sub is None or p.sub >= 50 or any(i.startswith(S.PART_LABELS[p.part]) for i in s.key_issues) for p in s.parts)


def test_brief_style_home_lands_in_poor():
    # brief example P10001: rating E, high gas+elec use, no solar, poor insulation, gas boiler, single glazing -> Poor (38)
    # typical E home: SAP 45, 160 kWh/m2 (above the York median 138), gas boiler rated Good (as 80% of York boilers are)
    h = make_home(rating="E", sap_score=45, baseline_gas_kwh=13000.0, baseline_elec_kwh=3000.0, walls_rating="Poor",
                  roof_rating="Poor", glazing="single", solar_pv=False, heating_type="gas_boiler", heating_rating="Good")
    s = S.score_home(h)
    assert s.classification == "Poor" and s.total == 37, s.total


# ---- after-retrofit ----

def test_after_score_keeps_epc_and_recomputes_changed_parts():
    h = make_home(glazing="single", controls="timer")
    before = S.score_home(h)
    after = S.score_after(h, [MeasureId.double_glazing], 12000.0 * 0.95, 3000.0)
    b = {p.part: p for p in before.parts}
    a = {p.part: p for p in after.parts}
    assert a["energy_efficiency"].sub == b["energy_efficiency"].sub
    assert a["energy_efficiency"].status == "unchanged_epc_not_reassessed"
    assert a["windows"].sub == 75 and a["smart_controls"].sub == b["smart_controls"].sub
    assert a["insulation"].sub == b["insulation"].sub and a["energy_intensity"].sub > b["energy_intensity"].sub


def test_retrofit_never_turns_missing_into_a_value():
    h = make_home(glazing=None)
    after = S.score_after(h, [MeasureId.double_glazing], 12000.0, 3000.0)
    assert "windows" in after.missing_parts
    before = S.score_home(h)
    assert after.total == before.total  # same energy, glazing still unknown -> no change


def test_state_effects_never_downgrade():
    h = make_home(roof_rating="Very Good", glazing="triple", controls="smart")
    h2 = S.apply_state_effects(h, [MeasureId.loft_insulation, MeasureId.double_glazing, MeasureId.smart_thermostat])
    assert (h2.roof_rating, h2.glazing, h2.controls) == ("Very Good", "triple", "smart")


def test_heat_pump_after_rating_at_least_good_and_floor_when_unknown():
    """D46: after a heat pump the heating rating is at least Good (York heat-pump certificates); with the rating
    unknown the heat-pump floor applies."""
    a = S.score_after(make_home(heating_rating="Poor"), [MeasureId.heat_pump], 300.0, 6000.0)
    assert next(p for p in a.parts if p.part == "heating").sub == 80
    a = S.score_after(make_home(heating_rating=None), [MeasureId.heat_pump], 300.0, 6000.0)
    assert next(p for p in a.parts if p.part == "heating").sub == 75
    assert S.apply_state_effects(make_home(heating_rating="Very Good", controls="none"),
                                 [MeasureId.heat_pump]).heating_rating == "Very Good"   # never downgraded
    assert S.apply_state_effects(make_home(controls="none"), [MeasureId.heat_pump]).controls == "full"


# ---- real data ----

@needs_data
def test_demo_a_hand_checked():
    from backend.app.data.loaders import get_home
    s = S.score_home(get_home(DEMO_A))
    x = (21616.666666666664 + 3766.6666666666665) / 171.0
    expect = {
        "energy_efficiency": 48.0,
        "energy_intensity": 100 * (186.022 - x) / (186.022 - 75.749),
        "insulation": (0.5 * 30 + 0.35 * 10) / 0.85,
        "heating": 80.0,
        "windows": 10 + 65 * 0.87,
        "renewables": 0.0,
        "smart_controls": 70.0,
    }
    got = {p.part: p.sub for p in s.parts}
    for k, v in expect.items():
        assert got[k] == pytest.approx(v, abs=1e-5), k
    raw = 0.25 * 48 + 0.2 * expect["energy_intensity"] + 0.15 * expect["insulation"] + 0.15 * 80 + 0.1 * 66.55 + 0 + 0.05 * 70
    assert s.raw_total == pytest.approx(raw, abs=1e-5)
    assert s.total == 44 and s.classification == "Poor"


@needs_data
def test_demo_c_unavailable():
    from backend.app.data.loaders import get_home
    s = S.score_home(get_home(DEMO_C))
    assert s.status == ValueStatus.unavailable and s.total is None and s.completeness == "1/7"


@needs_data
def test_a_rated_high_g_rated_low_across_dataset():
    import pandas as pd
    if not config.HOMES_SCORED.exists():
        pytest.skip("run pipelines/score_homes.py first")
    d = pd.read_parquet(config.HOMES_SCORED).dropna(subset=["score"])
    m = d.groupby("rating")["score"].mean()
    assert list(m.loc[list("ABCDEFG")]) == sorted(m.loc[list("ABCDEFG")], reverse=True)
    assert m["A"] >= 75 and m["G"] <= 35
