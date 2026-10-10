"""Code, not the LLM, decides what each sentence is and which measures it refers to."""

from backend.app.llm.claims import ExplanationText
from backend.app.llm.extract import extract_claims, split_sentences
from helpers import sheet_for

POOR = "york-demo-poor-semi"


def _text(**sections):
    return ExplanationText(**{k: sections.get(k, "") for k in ExplanationText.model_fields})


def test_sentence_split_keeps_placeholders_and_abbreviations():
    s = split_sentences("Gas falls by {energy_results.change.gas_saving_kwh}. E.g. this is fine, i.e. ok. "
                        "{derived.plan_order} comes next!")
    assert s == ["Gas falls by {energy_results.change.gas_saving_kwh}.", "E.g. this is fine, i.e. ok.",
                 "{derived.plan_order} comes next!"]


def test_types_are_inferred_from_values_and_wording():
    sheet = sheet_for(POOR)
    d = extract_claims(_text(
        energy="Gas use is estimated to fall by {energy_results.change.gas_saving_kwh}. Grid electricity is estimated "
               "to rise by {energy_results.change.grid_elec_saving_kwh}.",
        cost="Changes to bills in pounds are not estimated.",
        not_suitable="Solid wall insulation is not suitable, because {feasibility.solid_wall.reason}.",
        plan="We suggest {derived.plan_order}.",
        caveats="These are estimates."), sheet)
    types = {c.text.split()[0]: c.type for c in d.claims}
    assert types["Gas"] == "saving" and types["Grid"] == "increase" and types["Changes"] == "missing_data"
    assert types["Solid"] == "feasibility" and types["We"] == "recommendation" and types["These"] == "caveat"


def test_measures_come_from_placeholders_too():
    sheet = sheet_for(POOR)
    d = extract_claims(_text(plan="The plan is {derived.plan_order}.",
                             energy="With {energy_results.per_measure.2.measure}, gas use is estimated to fall by "
                                    "{energy_results.per_measure.2.gas_saving_kwh}."), sheet)
    plan = next(c for c in d.claims if c.section == "plan")
    assert set(plan.measures) == set(sheet.selected_measures)
    step = next(c for c in d.claims if c.section == "energy")
    assert step.measures == ["heat_pump"]
