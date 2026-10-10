"""The checker rejects every way an explanation can mislead, and the template always passes it."""

import pytest

import fake_engine as fe
from backend.app.llm.checker import check, check_rendered
from backend.app.llm.render import render
from helpers import add_claim, all_measure_sets, drop_claims, find, replace_claim, sheet_for, template_for

GAS = "energy_results.change.gas_saving_kwh"
ELEC = "energy_results.change.grid_elec_saving_kwh"
POOR = "york-demo-poor-semi"


def codes(errs):
    return {e.code for e in errs}


# --- The template invariant --------------------------------------------------

@pytest.mark.parametrize("pid", list(fe.HOMES))
def test_template_passes_for_every_demo_home(pid):
    sheet, draft = template_for(pid)
    assert check(draft, sheet) == []
    rendered = render(draft, sheet)
    assert check_rendered(rendered, sheet.scenario_id) == []


@pytest.mark.parametrize("pid", list(fe.HOMES))
def test_template_passes_for_every_measure_combination(pid):
    for measures in all_measure_sets(pid):
        sheet, draft = template_for(pid, measures)
        errs = check(draft, sheet)
        assert errs == [], (measures, [str(e) for e in errs])
        assert check_rendered(render(draft, sheet), sheet.scenario_id) == []


# --- Numbers only through placeholders ---------------------------------------

@pytest.fixture
def poor():
    return template_for(POOR)


def _energy_gas_index(draft):
    return find(draft, lambda c: c.section == "energy" and GAS in c.keys and c.type == "saving")


@pytest.mark.parametrize("text,code", [
    ("Gas use is estimated to fall by 11400 kWh a year.", "DIGIT"),
    ("Gas use is estimated to fall by about twelve thousand units.", "NUMBER_WORD"),
    ("Gas use is estimated to fall by half.", "NUMBER_WORD"),
    ("Gas use is estimated to fall by {energy_results.change.gas_saving_kwh} kWh.", "UNIT"),
    ("Gas use is estimated to fall by {energy_results.change.gas_saving_kwh}, a cut of {energy_results.change."
     "improvement_potential_pct}%.", "SYMBOL"),
    ("Gas use is estimated to fall by {Gas Saving}.", "BRACES"),
    ("Gas use is estimated to fall by {energy_results.change.oil_saving_kwh}.", "UNKNOWN_KEY"),
])
def test_number_leaks_are_rejected(poor, text, code):
    sheet, draft = poor
    bad = replace_claim(draft, _energy_gas_index(draft), text=text)
    assert code in codes(check(bad, sheet))


def test_co2_is_not_a_digit_leak(poor):
    sheet, draft = poor
    ok = replace_claim(draft, _energy_gas_index(draft),
                       text="Gas use is estimated to fall by {energy_results.change.gas_saving_kwh}, cutting CO2e.")
    assert "DIGIT" not in codes(check(ok, sheet))


def test_unavailable_value_only_in_missing_data_claims():
    sheet, draft = template_for(POOR)
    bad = add_claim(draft, section="cost", type="statement", text="Your bills change by {cost_results.bill_change_gbp}.",
                    keys=["cost_results.bill_change_gbp"])
    assert "UNAVAILABLE" in codes(check(bad, sheet))


# --- Direction of every change -------------------------------------------------

def test_electricity_increase_cannot_be_called_a_saving(poor):
    sheet, draft = poor
    i = find(draft, lambda c: c.section == "energy" and ELEC in c.keys)
    bad = replace_claim(draft, i, type="saving",
                        text="Grid electricity is estimated to fall by {energy_results.change.grid_elec_saving_kwh}.")
    assert "DIRECTION" in codes(check(bad, sheet))


def test_increase_no_longer_needs_abs(poor):
    sheet, draft = poor
    i = find(draft, lambda c: c.section == "energy" and ELEC in c.keys)
    ok = replace_claim(draft, i, text="Grid electricity is estimated to rise by "
                                      "{energy_results.change.grid_elec_saving_kwh}.")
    assert check(ok, sheet) == []


def test_reduction_described_as_rise_is_rejected(poor):
    sheet, draft = poor
    bad = replace_claim(draft, _energy_gas_index(draft),
                        text="Gas use is estimated to rise by {energy_results.change.gas_saving_kwh}.")
    assert "DIRECTION" in codes(check(bad, sheet))


def test_change_without_direction_is_rejected(poor):
    sheet, draft = poor
    i = find(draft, lambda c: c.section == "energy" and ELEC in c.keys)
    bad = replace_claim(draft, i, text="Grid electricity changes by {energy_results.change.grid_elec_saving_kwh}.")
    assert "DIRECTION" in codes(check(bad, sheet))


def test_mixed_directions_in_one_sentence_pass_when_each_is_right(poor):
    sheet, draft = poor
    good = add_claim(draft, section="energy", type="statement",
                     text="Gas use is estimated to fall by {energy_results.change.gas_saving_kwh}, while grid "
                          "electricity rises by {energy_results.change.grid_elec_saving_kwh}.")
    assert check(good, sheet) == []
    swapped = add_claim(draft, section="energy", type="statement",
                        text="Gas use is estimated to rise by {energy_results.change.gas_saving_kwh}, while grid "
                             "electricity falls by {energy_results.change.grid_elec_saving_kwh}.")
    assert "DIRECTION" in codes(check(swapped, sheet))


def test_zero_change_cannot_be_called_a_rise():
    sheet, draft = template_for("york-demo-flat")  # electricity change is exactly zero
    bad = add_claim(draft, section="energy", type="statement",
                    text="Grid electricity is estimated to rise by {energy_results.change.grid_elec_saving_kwh}.")
    assert "DIRECTION" in codes(check(bad, sheet))


def test_direction_word_belongs_to_its_own_placeholder(poor):
    sheet, draft = poor  # per_measure.0: gas saving > 0, electricity change == 0
    ok = add_claim(draft, section="energy", type="statement",
                   text="Loft insulation saves {energy_results.per_measure.0.gas_saving_kwh} of gas and changes "
                        "electricity by {energy_results.per_measure.0.elec_saving_kwh}.")
    assert check(ok, sheet) == []


def test_saying_an_available_figure_is_not_estimated_is_rejected(poor):
    sheet, draft = poor  # the poor semi has an indicative value range
    bad = add_claim(draft, section="value", type="missing_data",
                    text="A property value change is not estimated because the valuation is {valuation.status}.")
    assert "CONTRADICTION" in codes(check(bad, sheet))


# --- Comparisons ----------------------------------------------------------------

def test_unverified_comparative_is_rejected(poor):
    sheet, draft = poor
    bad = replace_claim(draft, _energy_gas_index(draft),
                        text="Gas use is estimated to fall by {energy_results.change.gas_saving_kwh}, more than "
                             "anything else.")
    assert "COMPARATIVE" in codes(check(bad, sheet))


def test_superlative_allowed_with_code_ranked_fact(poor):
    sheet, draft = poor
    ok = add_claim(draft, section="energy", type="statement",
                   text="The largest estimated gas saving comes from {derived.largest_gas_saving_measure}.")
    assert check(ok, sheet) == []


# --- Feasibility ------------------------------------------------------------------

def test_infeasible_measure_cannot_be_recommended(poor):
    sheet, draft = poor
    bad = add_claim(draft, section="plan", type="recommendation", text="Solid wall insulation would also help.",
                    measures=["solid_wall"])
    assert "INFEASIBLE" in codes(check(bad, sheet))


def test_infeasible_measure_cannot_be_suggested_in_a_statement(poor):
    sheet, draft = poor
    bad = add_claim(draft, section="caveats", type="statement", text="You should also install solid wall insulation.")
    assert "INFEASIBLE" in codes(check(bad, sheet))


def test_recommendation_must_be_in_selected_plan(poor):
    sheet, draft = poor
    bad = add_claim(draft, section="plan", type="recommendation", text="Double glazing is part of the plan.",
                    measures=["double_glazing"])
    assert "NOT_IN_PLAN" in codes(check(bad, sheet))


def test_feasibility_claim_about_feasible_measure_is_rejected(poor):
    sheet, draft = poor
    bad = add_claim(draft, section="not_suitable", type="feasibility", text="Loft insulation is not suitable.",
                    measures=["loft_insulation"])
    assert "FEASIBILITY" in codes(check(bad, sheet))


def test_every_infeasible_measure_must_be_explained(poor):
    sheet, draft = poor
    bad = drop_claims(draft, lambda c: c.type == "feasibility")
    assert "COVERAGE" in codes(check(bad, sheet))


def test_needs_verification_recommendation_must_say_check():
    sheet = sheet_for("york-demo-flat", ["cavity_wall", "heat_pump"])
    from backend.app.llm.templates import template_report
    draft = template_report(sheet)
    assert check(draft, sheet) == []
    bad = add_claim(draft, section="plan", type="recommendation", text="A heat pump is in the plan.",
                    measures=["heat_pump"])
    assert "VERIFY" in codes(check(bad, sheet))


# --- Banned phrases and provenance -------------------------------------------------

@pytest.mark.parametrize("text", [
    "The retrofit will definitely pay off.",
    "Your savings are guaranteed.",
    "This will increase your home's value.",
    "Talk to your lender about a green mortgage.",
    "A Daikin unit would suit this home.",
    "This is a proven effect of insulation.",
])
def test_banned_phrases(poor, text):
    sheet, draft = poor
    bad = add_claim(draft, section="caveats", type="caveat", text=text)
    assert "BANNED" in codes(check(bad, sheet))


def test_negated_banned_words_are_allowed(poor):
    sheet, draft = poor
    ok = add_claim(draft, section="caveats", type="caveat", text="This is not a guarantee and it is not proven.")
    ok = add_claim(ok, section="caveats", type="caveat", text="It is based on past sales rather than a guaranteed result.")
    assert check(ok, sheet) == []


def test_modelled_baseline_cannot_be_called_actual_usage(poor):
    sheet, draft = poor
    bad = add_claim(draft, section="caveats", type="caveat", text="These are based on your actual gas usage.")
    assert "PROVENANCE" in codes(check(bad, sheet))


def test_user_provided_baseline_can_be_called_actual_usage():
    sheet, draft = template_for("york-demo-conflict")
    ok = add_claim(draft, section="caveats", type="caveat", text="These are based on your actual gas usage.")
    assert "PROVENANCE" not in codes(check(ok, sheet))


# --- Coverage and wording -------------------------------------------------------------

def test_warnings_must_be_passed_on(poor):
    sheet, draft = poor
    bad = drop_claims(draft, lambda c: any(k.startswith("warnings.") for k in c.keys))
    assert "COVERAGE" in codes(check(bad, sheet))


def test_both_fuels_must_be_reported(poor):
    sheet, draft = poor
    bad = drop_claims(draft, lambda c: ELEC in c.keys)
    errs = check(bad, sheet)
    assert any("electricity" in e.message for e in errs)


def test_value_section_required_even_when_not_estimated():
    sheet, draft = template_for("york-demo-flat")
    bad = drop_claims(draft, lambda c: c.section == "value")
    assert "COVERAGE" in codes(check(bad, sheet))


def test_value_must_be_called_indicative(poor):
    sheet, draft = poor
    i = find(draft, lambda c: c.section == "value" and c.type == "statement")
    bad = replace_claim(draft, i, text=draft.claims[i].text.replace("indicative", "rough"))
    assert "WORDING" in codes(check(bad, sheet))


def test_savings_must_be_called_estimates(poor):
    sheet, draft = poor
    bad = drop_claims(draft, lambda c: c.section == "energy" and "estimat" in c.text.lower()
                      and GAS not in c.keys and ELEC not in c.keys)
    for i, c in enumerate(bad.claims):
        if c.section == "energy":
            bad = replace_claim(bad, i, text=c.text.replace("estimated to ", "going to ").replace("estimates", "figures"))
    assert "WORDING" in codes(check(bad, sheet))


def test_missing_inputs_must_be_acknowledged():
    sheet, draft = template_for("york-demo-missing")
    bad = drop_claims(draft, lambda c: c.type == "missing_data")
    assert "COVERAGE" in codes(check(bad, sheet))


# --- Post-render -------------------------------------------------------------------

def test_stale_scenario_is_rejected(poor):
    sheet, draft = poor
    other = sheet_for(POOR, ["loft_insulation"])
    assert other.scenario_id != sheet.scenario_id
    errs = check_rendered(render(draft, sheet), other.scenario_id)
    assert "STALE" in codes(errs)



def test_not_simply_added_is_rejected(poor):
    sheet, draft = poor  # per-measure savings come from a sequential simulation and do add up
    bad = add_claim(draft, section="energy", type="caveat",
                    text="The measures interact, so their estimated savings are not simply added together.")
    assert "INTERACTION" in codes(check(bad, sheet))


def test_interaction_talk_needs_more_than_one_measure():
    sheet, draft = template_for(POOR, ["loft_insulation"])
    bad = add_claim(draft, section="energy", type="caveat",
                    text="These estimates allow for how the measures interact.")
    assert "INTERACTION" in codes(check(bad, sheet))


def test_change_filter_needs_no_direction_word_but_rejects_contradiction(poor):
    sheet, draft = poor
    ok = add_claim(draft, section="energy", type="statement",
                   text="Grid electricity is estimated to {energy_results.change.grid_elec_saving_kwh|change}.")
    assert check(ok, sheet) == []
    bad = add_claim(draft, section="energy", type="statement",
                    text="The electricity saving is estimated to {energy_results.change.grid_elec_saving_kwh|change}.")
    assert "DIRECTION" in codes(check(bad, sheet))


def test_needs_verification_measure_cannot_be_called_unsuitable():
    sheet, draft = template_for("york-demo-missing")  # cavity wall: needs verification (wall type unknown)
    bad = add_claim(draft, section="not_suitable", type="feasibility",
                    text="Cavity wall insulation is not suitable because {feasibility.cavity_wall.reason}.")
    assert "NEEDS_CHECK" in codes(check(bad, sheet))


def test_plan_order_carries_the_needs_check_caveat():
    sheet, draft = template_for("york-demo-missing", ["loft_insulation", "cavity_wall"])
    assert "needs checking" in sheet.value("derived.plan_order")
    ok = add_claim(draft, section="plan", type="recommendation", text="The plan is {derived.plan_order}.")
    assert check(ok, sheet) == []
