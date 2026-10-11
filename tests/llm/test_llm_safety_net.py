"""Keyword safety net for what-if parsing (D44): an LLM that misreads an explicit request as 'no change' is
overridden by the keyword reading; stated context facts it dropped are kept; out_of_scope is never overridden."""

import fake_engine as fe
import synthetic_homes as sh
from backend.app.llm.advise import advise_whatif, keep_stated_context
from backend.app.llm.claims import WhatIfParse
from backend.app.llm.whatif import answer_whatif, keyword_parse, reconcile_parse
from helpers import FakeLLM

POOR = "york-demo-poor-semi"
BASE = ["loft_insulation", "cavity_wall"]


def _p(kind="question_about_current", **kw) -> WhatIfParse:
    return WhatIfParse(kind=kind, add=kw.pop("add", []), remove=kw.pop("remove", []),
                       unsupported=kw.pop("unsupported", []), **kw)


def test_q29_llm_reads_add_heat_pump_as_no_change():
    base = fe.run(POOR, BASE)
    a = answer_whatif(base, "What if I add a heat pump?", fe.run, use_llm=True, client=FakeLLM(_p()))
    assert a.outcome.parser == "llm+keywords" and a.outcome.added == ["heat_pump"] and a.recalculated
    assert "rise" in a.explanation.rendered.all_text   # electricity rises with a heat pump


def test_q44_explicit_infeasible_request_is_blocked_not_ignored():
    base = fe.run(POOR, BASE)
    a = answer_whatif(base, "Add solid wall insulation please", fe.run, use_llm=True, client=FakeLLM(_p()))
    assert a.outcome.parser == "llm+keywords" and a.outcome.blocked == ["solid_wall"] and not a.recalculated
    assert "not suitable" in a.explanation.rendered.all_text.lower()


def test_llm_out_of_scope_is_never_overridden():
    base = fe.run(POOR, BASE)
    a = answer_whatif(base, "Add a heat pump and find me a mortgage for it", fe.run, use_llm=True,
                      client=FakeLLM(_p("out_of_scope", unsupported=["mortgage"])))
    assert a.outcome.kind == "out_of_scope" and a.outcome.parser == "llm" and not a.recalculated


def test_llm_reading_with_a_change_wins_over_keywords():
    llm = _p("change_measures", add=["solar_pv"])
    parsed, src = reconcile_parse(llm, keyword_parse("What if I add a heat pump?", BASE), BASE)
    assert src == "llm" and parsed.add == ["solar_pv"]


def test_no_op_keyword_reading_does_not_override():
    # the keyword reading asks for a measure already in the plan: no explicit change, the LLM reading stands
    parsed, src = reconcile_parse(_p(), keyword_parse("add loft insulation", BASE), BASE)
    assert src == "llm" and parsed.kind == "question_about_current"


def test_context_facts_the_llm_read_are_kept_when_keywords_win():
    llm = _p(budget_gbp=8000, role="owner_occupier")
    parsed, src = reconcile_parse(llm, keyword_parse("My budget is £8,000, what if I add a heat pump?", BASE), BASE)
    assert src == "llm+keywords" and parsed.add == ["heat_pump"] and parsed.budget_gbp == 8000
    assert parsed.role == "owner_occupier"


def test_keep_stated_context_unions_and_respects_llm_values():
    llm = _p("update_context", role="tenant", budget_gbp=3000, rejected=["heat_pump"])
    out = keep_stated_context(llm, {"budget_gbp": 9999, "horizon": "lt2", "rejected": ["solar_pv"]})
    assert out.budget_gbp == 3000 and out.horizon == "lt2" and out.rejected == ["heat_pump", "solar_pv"]
    assert keep_stated_context(llm, {"budget_gbp": 3000}) is llm   # nothing new: unchanged


def test_q40_budget_kept_when_llm_reads_out_of_scope():
    res = advise_whatif("syn-poor-semi", "My budget is £5,000. What should I do?", sh.run, use_llm=True,
                        client=FakeLLM(_p("out_of_scope", unsupported=["budget advice"])))
    assert res.updated_context and res.context.budget_gbp == 5000
    assert "budget" in res.explanation.rendered.all_text.lower()


def test_q40_budget_kept_when_llm_reads_no_change():
    res = advise_whatif("syn-poor-semi", "My budget is £5,000. What should I do?", sh.run, use_llm=True,
                        client=FakeLLM(_p()))
    assert res.updated_context and res.context.budget_gbp == 5000


def test_null_lists_from_the_model_are_empty_lists():
    """gpt-oss-20b answers null for empty lists; that must not invalidate the whole parse (it fell to keywords)."""
    p = WhatIfParse.model_validate({"kind": "change_measures", "add": ["heat_pump"], "remove": None, "unsupported": None,
                                    "priorities": None, "constraints": None, "completed": None, "rejected": None})
    assert p.add == ["heat_pump"] and p.remove == [] and p.priorities == [] and p.rejected == []
