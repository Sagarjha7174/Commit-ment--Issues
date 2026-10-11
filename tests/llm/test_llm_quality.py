"""Explanation quality fixes (D45): no code phrases spliced into LLM grammar, no unlabelled fragments, every sentence
ends with a full stop, each caveat once, payback and loan always covered, colour by good/bad for the homeowner."""
import re

import synthetic_homes as sh
from backend.app.llm.explain import explain_sheet
from backend.app.llm.facts_view import build_factsheet
from backend.app.llm.render import render
from backend.app.llm.templates import template_report
from helpers import FakeLLM, as_text

HOME = "syn-poor-semi"


def _sheet():
    return build_factsheet(sh.run(HOME))


def _llm_text(sheet, **sections):
    """A clean LLM answer (the template's prose) with some sections replaced."""
    return as_text(template_report(sheet)).model_copy(update=sections)


def test_a_direction_filter_never_spliced_into_llm_sentence():
    sheet = _sheet()
    assert sheet.get("epc_change.sap_change").available
    bad = ("The EPC rating improves, with the SAP score {epc_change.sap_change|changes} to "
           "{epc_change.sap_after_indicative}.")
    res = explain_sheet(sheet, client=FakeLLM(_llm_text(sheet, score=as_text(template_report(sheet)).score + " " + bad)))
    assert any("[FILTER]" in e for d in res.dropped for e in d["errors"])
    text = res.rendered.all_text
    assert "with the SAP score goes up" not in text and "score goes up by" not in text.split("with the SAP score")[-1][:5]
    assert re.search(r"EPC score goes up by \d+ points", text)   # the template's own sentence, whole


def test_b_bare_placeholder_fragments_are_rejected_and_labels_kept():
    sheet = _sheet()
    res = explain_sheet(sheet, client=FakeLLM(_llm_text(sheet, issues="{derived.issues}",
                                                         caveats="{assumptions} {warnings.0}")))
    assert sum("[FRAGMENT]" in e for d in res.dropped for e in d["errors"]) >= 2
    text = res.rendered.all_text
    assert "Key issues: " in text and "Main assumptions: " in text


def test_b_every_rendered_sentence_ends_with_a_full_stop():
    sheet = _sheet()
    for c in (c for s in render(template_report(sheet), sheet).sections for c in s.claims):
        assert c.text.rstrip()[-1] in ".!?", c.text


def test_c_each_caveat_once():
    sheet = _sheet()
    bench = re.compile(r"\b(benchmark|not a meter|meter readings?)\b", re.I)
    template_caveats = [c.text for s in render(template_report(sheet), sheet).sections if s.id == "caveats"
                        for c in s.claims]
    assert sum(bool(bench.search(t)) for t in template_caveats) == 1
    # an LLM that restates the benchmark caveat next to the warning that already says it
    llm = _llm_text(sheet, caveats=" ".join(f"Note: {{{k}}}." for k in sheet.warning_keys)
                    + " The starting energy use is a benchmark for similar homes, not this home's meter readings."
                    + " All of these figures are estimates, not guarantees.")
    res = explain_sheet(sheet, client=FakeLLM(llm))
    caveats = [c.text for s in res.rendered.sections if s.id == "caveats" for c in s.claims]
    assert sum(bool(bench.search(t)) for t in caveats) == 1, caveats
    assert len(caveats) == len(set(caveats))


def test_c_a_sentence_carrying_two_caveats_is_kept_for_the_one_said_nowhere_else():
    """Real-LLM eval q20: "... a benchmark, not this home's meter readings, and the savings are estimates, not
    guarantees." was dropped as a benchmark repeat, losing the only estimates caveat (the answer fell to the template)."""
    scenario = sh.run(HOME)
    scenario["warnings"] = [*scenario["warnings"], "The starting energy use is a benchmark: the typical use of similar "
                                                   "homes in the region, not this home's meter readings."]
    sheet = build_factsheet(scenario)   # an engine warning already says "benchmark", as on York homes
    both = "The starting energy use is a benchmark, not this home's meter readings, and the savings are estimates, " \
           "not guarantees."
    llm = _llm_text(sheet, caveats=" ".join(f"Note: {{{k}}}." for k in sheet.warning_keys) + " " + both)
    res = explain_sheet(sheet, client=FakeLLM(llm))
    assert res.source == "llm_patched", res.fallback_reason
    caveats = " ".join(c.text for s in res.rendered.sections if s.id == "caveats" for c in s.claims)
    assert "estimates, not guarantees" in caveats


def test_d_payback_and_loan_filled_when_the_llm_omits_them():
    sheet = _sheet()
    assert sheet.get("cost_results.payback_years") is not None and sheet.get("cost_results.loan_monthly_repayment_gbp").available
    cost = "The selected measures are estimated to cost about {cost_results.package_cost_gbp} in total before grants. " \
           "At today's capped energy prices, the annual energy bill is estimated to fall by {cost_results.bill_saving_gbp}."
    res = explain_sheet(sheet, client=FakeLLM(_llm_text(sheet, cost=cost)))
    cost_text = " ".join(c.text for s in res.rendered.sections if s.id == "cost" for c in s.claims)
    assert re.search(r"payback", cost_text, re.I) and "illustrative loan" in cost_text
    assert res.source == "llm_patched" and res.template_filled >= 2


def test_e_colour_follows_good_or_bad_for_the_homeowner():
    sheet = _sheet()
    assert sheet.get("epc_change.sap_change").sentiment == "good"          # SAP up: good, though "up"
    assert sheet.get("epc_change.sap_change").direction == "up"
    elec = sheet.get("energy_results.change.grid_elec_saving_kwh")
    assert elec.direction == "increase" and elec.sentiment == "bad"          # heat pump: electricity rises
    assert sheet.get("energy_results.change.gas_saving_kwh").sentiment == "good"
    assert sheet.get("cost_results.bill_saving_gbp").sentiment in ("good", "bad")
    spans = [sp for s in render(template_report(sheet), sheet).sections for c in s.claims for sp in c.spans]
    epc = next(sp for sp in spans if sp.key == "epc_change.sap_change")
    assert epc.sentiment == "good" and epc.direction == "up"


def test_e_extra_cost_is_bad_and_cheaper_is_good():
    from backend.app.llm.facts_view import Fact
    assert Fact("diff.extra_cost_gbp", 500.0, "gbp_change", "x").sentiment == "bad"
    assert Fact("diff.extra_cost_gbp", -500.0, "gbp_change", "x").sentiment == "good"
    assert Fact("k", 0.0, "kwh_change", "x").sentiment == "neutral"
    assert Fact("k", 10.0, "kwh", "x").sentiment is None   # not a change: no colour


def test_heat_pump_epc_caveat_only_when_it_replaces_gas(monkeypatch):
    """D46: replacing electric heating raises the EPC; the 'can lower the EPC' caveat is for gas homes only."""
    from backend.app.llm.checker import check_claim, heat_pump_replaces_gas
    from backend.app.llm.claims import Claim
    gas_home = _sheet()
    assert heat_pump_replaces_gas(gas_home)
    assert any("can lower the EPC" in c.text for s in render(template_report(gas_home), gas_home).sections
               for c in s.claims)
    # an electrically heated home (canonical heating type 'electric', as in the York build): the heat pump replaces
    # electric heating, which the NEED electric split (D16) makes estimable
    monkeypatch.setitem(sh.HOMES, "syn-electric-hp", {**sh.HOMES["syn-electric-terrace"], "heating_type": "electric"})
    electric = build_factsheet(sh.run("syn-electric-hp", ["heat_pump"]))
    caveat = Claim(section="caveats", type="caveat", text="A heat pump cuts carbon, but it can lower the EPC (SAP) rating.")
    assert "heat_pump" in electric.estimated_measures and not heat_pump_replaces_gas(electric)
    assert not any("can lower the EPC" in c.text for s in render(template_report(electric), electric).sections
                   for c in s.claims)
    assert any(e.code == "CONTRADICTION" for e in check_claim(0, caveat, electric, llm=True))
    assert not any(e.code == "CONTRADICTION" for e in check_claim(0, caveat, gas_home, llm=True))
