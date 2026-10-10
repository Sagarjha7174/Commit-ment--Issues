"""The LLM layer on the team's REAL engine (backend/app/services), using the synthetic homes in
eval/synthetic_homes.py (York data is not in git)."""

import pytest

pytest.importorskip("pandas")  # the engine's data loader needs it

import synthetic_homes as sh  # noqa: E402
from backend.app.llm.checker import check, check_rendered  # noqa: E402
from backend.app.llm.engine_map import plain_warnings  # noqa: E402
from backend.app.llm.facts_view import build_factsheet  # noqa: E402
from backend.app.llm.render import render  # noqa: E402
from backend.app.llm.templates import template_report  # noqa: E402
from backend.app.llm.whatif import answer_whatif  # noqa: E402


def _subsets(pid):
    import itertools
    sheet = build_factsheet(sh.run(pid))
    usable = [m for m, f in sheet.feasibility.items() if f.state != "infeasible"]
    for r in range(len(usable) + 1):
        yield from (list(c) for c in itertools.combinations(usable, r))


@pytest.mark.parametrize("pid", list(sh.HOMES))
def test_template_passes_for_every_measure_combination_on_real_engine(pid):
    for measures in _subsets(pid):
        sheet = build_factsheet(sh.run(pid, measures))
        draft = template_report(sheet)
        errs = check(draft, sheet)
        assert errs == [], (pid, measures, [str(e) for e in errs])
        assert check_rendered(render(draft, sheet), sheet.scenario_id) == []


def test_engine_facts_map_to_contract():
    sheet = build_factsheet(sh.run("syn-poor-semi"))
    assert sheet.selected_measures and sheet.get("energy_results.change.gas_saving_kwh").direction == "reduction"
    assert sheet.get("energy_results.change.grid_elec_saving_kwh").direction == "increase"  # heat pump
    assert sheet.get("carbon_results.saving_kg").available
    assert sheet.feasibility["solid_wall"].state == "infeasible" and sheet.feasibility["solid_wall"].reason
    # value gate enabled (D38): indicative range given; no outward code on synthetic homes -> no GBP value, with a reason
    assert sheet.get("valuation.uplift_low_pct").available and sheet.value("valuation.status") == "exploratory"
    assert sheet.value("valuation.uplift_low_pct") <= sheet.value("valuation.uplift_high_pct")
    assert not sheet.get("valuation.current_value_gbp").available and sheet.get("valuation.current_value_gbp.reason")
    text = " ".join(str(f.value) for f in sheet.facts.values() if f.kind in ("text", "text_list") and f.available)
    assert "docs/" not in text and "D14" not in text  # internal references never reach homeowners


def test_user_provided_baseline_counts_as_measured():
    assert build_factsheet(sh.run("syn-conflict")).baseline_provenance == {"user-provided"}


def test_no_baseline_means_not_estimated():
    sheet = build_factsheet(sh.run("syn-no-baseline"))
    assert sheet.get("energy_results.change.gas_saving_kwh").status != "available"
    assert sheet.get("carbon_results.saving_kg").status != "available"


def test_plain_warnings():
    out = plain_warnings(["heat_pump: impact not validated against NEED (brief range / assumption)",
                          "double_glazing: impact not validated against NEED (brief range / assumption)",
                          "all savings are estimates, not guarantees"])
    assert out == ["The savings for a heat pump and double glazing use typical published ranges, not measured UK data."]


def test_whatif_on_real_engine_recomputes_and_blocks():
    base = sh.run("syn-poor-semi", ["loft_insulation", "cavity_wall"])
    a = answer_whatif(base, "What if I add a heat pump?", sh.run, use_llm=False)
    assert a.recalculated and a.explanation.scenario_id != base["scenario_id"]
    assert "rise" in a.explanation.rendered.all_text
    b = answer_whatif(base, "add solid wall insulation", sh.run, use_llm=False)
    assert not b.recalculated and b.outcome.blocked == ["solid_wall"]
