"""Package search: hand-built selection cases (known optimum), every fallback, and real-home properties.
Baseline emissions in the hand-built cases are 1,000 kg/yr, so carbon_pct = carbon / 10."""
import pytest

from backend.app.schemas.enums import MeasureId as M, ValueStatus
from backend.app.services import packages as P
from backend.app.services import sensitivity
from backend.app.services.baseline import get_baseline
from backend.app.services.feasibility import assess
from tests.conftest import DEMO_A, make_home, needs_data


def C(pid, cost, carbon, purchased, confirmed=True, verify=()):
    n = 0 if pid == "none" else pid.count("+") + 1
    return P.Cand(pid, cost, carbon, purchased, n, confirmed, carbon / 10.0, list(verify))


NONE = C("none", 0.0, 0.0, 0.0)


def picks(cands, **kw):
    f, fb = P.select_featured(cands, **kw)
    return {p.objective: p.package_id for p in f}, fb, f


HAND_CASES = [
    # (name, candidates, budget, expected {objective: package})
    ("tie_on_per_pound_prefers_larger_carbon",
     [NONE, C("a", 100, 50, 200), C("b", 500, 200, 800), C("a+b", 600, 240, 950)], None,
     {"lowest_cost_meeting_threshold": "b", "largest_carbon_saving": "a+b", "best_carbon_per_pound": "a+b"}),
    ("budget_excludes_expensive_package",
     [NONE, C("a", 100, 50, 200), C("b", 500, 200, 800), C("a+b", 600, 240, 950)], 550.0,
     {"lowest_cost_meeting_threshold": "b", "largest_carbon_saving": "b", "best_carbon_per_pound": "b"}),
    ("dominated_package_never_featured",
     [NONE, C("b", 500, 200, 800), C("c", 800, 150, 600)], None,
     {"lowest_cost_meeting_threshold": "b", "largest_carbon_saving": "b", "best_carbon_per_pound": "b"}),
    ("cost_tie_prefers_larger_carbon",
     [NONE, C("a", 500, 150, 900), C("b", 500, 200, 800)], None,
     {"lowest_cost_meeting_threshold": "b", "largest_carbon_saving": "b", "best_carbon_per_pound": "b"}),
    ("three_objectives_three_answers",
     [NONE, C("a", 200, 110, 400), C("b", 1000, 900, 3000), C("a+b", 1200, 950, 3300)], None,
     {"lowest_cost_meeting_threshold": "a", "largest_carbon_saving": "a+b", "best_carbon_per_pound": "b"}),
    ("conditional_cannot_displace_confirmed",
     [NONE, C("a", 500, 200, 800), C("b", 400, 300, 900, confirmed=False, verify=["b (roof)"])], None,
     {"lowest_cost_meeting_threshold": "a", "largest_carbon_saving": "a", "best_carbon_per_pound": "a"}),
    ("threshold_exactly_met",
     [NONE, C("a", 100, 100, 300), C("b", 50, 99.9, 290)], None,
     {"lowest_cost_meeting_threshold": "a", "largest_carbon_saving": "a", "best_carbon_per_pound": "a"}),
    ("four_measures_budget_mid",
     [NONE, C("l", 1050, 120, 600), C("c", 1000, 460, 2500), C("t", 400, 170, 950), C("c+l", 2050, 560, 3100),
      C("c+t", 1400, 600, 3300), C("l+t", 1450, 280, 1500), C("c+l+t", 2450, 690, 3800)], 1500.0,
     {"lowest_cost_meeting_threshold": "t", "largest_carbon_saving": "c+t", "best_carbon_per_pound": "c"}),
    ("four_measures_no_budget",
     [NONE, C("l", 1050, 120, 600), C("c", 1000, 460, 2500), C("t", 400, 170, 950), C("c+l", 2050, 560, 3100),
      C("c+t", 1400, 600, 3300), C("l+t", 1450, 280, 1500), C("c+l+t", 2450, 690, 3800)], None,
     {"lowest_cost_meeting_threshold": "t", "largest_carbon_saving": "c+l+t", "best_carbon_per_pound": "c"}),
    ("heat_pump_raises_purchased_but_cuts_carbon",
     [NONE, C("i", 1000, 150, 800), C("hp", 17500, 2000, -500), C("hp+i", 18500, 2100, -300)], None,
     {"lowest_cost_meeting_threshold": "i", "largest_carbon_saving": "hp+i", "best_carbon_per_pound": "i"}),
    ("per_pound_tie_full_break_by_cost",
     [NONE, C("a", 200, 200, 500), C("b", 400, 400, 500)], None,
     {"lowest_cost_meeting_threshold": "a", "largest_carbon_saving": "b", "best_carbon_per_pound": "b"}),
]


@pytest.mark.parametrize("name,cands,budget,expect", HAND_CASES, ids=[c[0] for c in HAND_CASES])
def test_hand_built_optimum(name, cands, budget, expect):
    got, fb, featured = picks(cands, budget=budget)
    assert got == expect and fb == []
    dom = P.pareto([c for c in cands if c.confirmed])
    assert all(dom[p] is None for p in got.values())
    assert all("best overall" not in f.label.lower() for f in featured)


def test_fallback_threshold_not_met():
    got, fb, f = picks([NONE, C("a", 100, 50, 200), C("b", 300, 80, 400)])
    assert fb == ["no package meets the selection threshold (10% of baseline emissions)"]
    assert got["largest_carbon_saving"] == "b"
    assert got["lowest_cost_meeting_threshold"] is None and got["best_carbon_per_pound"] is None
    assert next(x for x in f if x.objective == "lowest_cost_meeting_threshold").alternatives == ["b", "a"]


def test_fallback_no_cost_data():
    got, fb, _ = picks([C("none", None, 0, 0), C("a", None, 150, 500), C("b", None, 300, 900)])
    assert fb == ["no valid cost data: carbon options shown without cost rankings"]
    assert got == {"lowest_cost_meeting_threshold": None, "largest_carbon_saving": "b", "best_carbon_per_pound": None}


def test_fallback_no_emissions_cut():
    got, fb, f = picks([NONE, C("a", 100, -20, 500), C("b", 200, -5, -100)])
    assert fb and fb[0].startswith("no package cuts emissions")
    assert set(got.values()) == {None} and f[0].alternatives == ["a", "b"]


def test_fallback_only_conditional():
    got, fb, _ = picks([NONE, C("a", 100, 300, 500, confirmed=False, verify=["a (glazing)"])])
    assert fb == ["only conditional packages: verify a (glazing) before choosing"]
    assert set(got.values()) == {None}


def test_threshold_never_silently_lowered():
    got, _, _ = picks([NONE, C("a", 100, 99.99, 200)])
    assert got["lowest_cost_meeting_threshold"] is None


# ---- real homes ----

def _search(home, **kw):
    b = get_baseline(home)
    f = assess(home)
    return P.search(home, b, f, **kw), b, f


def test_do_nothing_always_present_and_deterministic():
    h = make_home(glazing="single", controls="timer")
    s1, _, _ = _search(h)
    s2, _, _ = _search(h)
    ids = [p.package_id for p in s1.packages]
    assert "none" in ids and ids == [p.package_id for p in s2.packages]
    assert len(ids) == len(set(ids)) == 2 ** 6  # solid wall infeasible on cavity walls -> 6 candidates
    assert s1.model_dump() == s2.model_dump()


def test_featured_not_dominated_and_confirmed_real():
    h = make_home(glazing="single", controls="timer")
    s, _, _ = _search(h)
    by = {p.package_id: p for p in s.packages}
    for f in s.featured:
        if f.package_id:
            p = by[f.package_id]
            assert not p.dominated and p.confirmed and p.eligible_for_cost_comparison


def test_conditional_packages_marked():
    h = make_home(glazing=None)
    s, _, _ = _search(h)
    dg = [p for p in s.packages if M.double_glazing in p.measures]
    assert dg and all(not p.confirmed and p.must_verify for p in dg)


def test_combination_warning_and_unvalidated_listed():
    h = make_home(glazing="single", controls="timer")
    s, _, _ = _search(h)
    p = next(p for p in s.packages if p.package_id == "cavity_wall+loft_insulation")
    assert p.warnings == [P.COMBO_WARNING]
    q = next(p for p in s.packages if p.package_id == "double_glazing+heat_pump")
    assert set(q.unvalidated_impacts) == {"double_glazing", "heat_pump"}


def test_missing_baseline_gives_fallback():
    h = make_home(baseline_gas_kwh=None, gas_status="unknown_mains_gas")
    s, _, _ = _search(h)
    assert s.fallbacks == ["baseline unavailable: no packages estimated"]
    assert all(f.package_id is None for f in s.featured)


def test_sensitivity_runs_and_labels():
    h = make_home(glazing="single", controls="timer")
    s, b, f = _search(h)
    r = sensitivity.run(h, b, f, s)
    assert "not a confidence interval" in r["label"] and len(r["runs"]) == 13
    assert set(r["survival"]) == {"lowest_cost_meeting_threshold", "largest_carbon_saving", "best_carbon_per_pound"}
    assert "roof orientation and shading (PV yield)" in r["untested"]
    for obj, sv in r["survival"].items():
        if sv["base_pick"]:
            assert next(p for p in s.packages if p.package_id == sv["base_pick"]).sensitivity[obj] == sv


@needs_data
def test_demo_a_packages():
    from backend.app.data.loaders import get_home
    s, _, _ = _search(get_home(DEMO_A))
    # demo A's roof is flat (D20): loft insulation is infeasible, so 5 candidate measures -> 32 packages
    assert len(s.packages) == 32 and s.excluded_measures == {"loft_insulation": "infeasible: flat_roof",
                                                             "solid_wall": "infeasible: not_solid_wall"}
    assert {f.objective: f.package_id for f in s.featured}["lowest_cost_meeting_threshold"] == "cavity_wall"
    assert all(p.status == ValueStatus.ok for p in s.packages)
