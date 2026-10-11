"""Decision context (product concept): permissions, plan choice, context parsing, memory, and the template
invariant for every role on the real engine."""

import pytest

pytest.importorskip("pandas")

import synthetic_homes as sh  # noqa: E402
from backend.app.llm import memory  # noqa: E402
from backend.app.llm.advise import advise, advise_whatif, keyword_context  # noqa: E402
from backend.app.llm.checker import check, check_rendered  # noqa: E402
from backend.app.llm.claims import Claim, ExplanationDraft  # noqa: E402
from backend.app.llm.context import Excluded, UserContext, decide, permissions  # noqa: E402
from backend.app.llm.facts_view import build_factsheet, canonical  # noqa: E402
from backend.app.llm.render import render  # noqa: E402
from backend.app.llm.templates import template_report  # noqa: E402

PERSONAS = {
    "tenant_short": UserContext(role="tenant", horizon="lt2"),
    "owner_budget": UserContext(role="owner_occupier", budget_gbp=3000),
    "seller": UserContext(role="selling"),
    "landlord": UserContext(role="landlord"),
    "owner_long_carbon": UserContext(role="owner_occupier", horizon="y10_plus", priorities=["carbon"]),
    "listed": UserContext(role="owner_occupier", constraints=["listed_or_conservation"]),
    "exterior_locked": UserContext(constraints=["cannot_alter_exterior", "no_roof_access"]),
    "memory": UserContext(completed=["loft_insulation"], rejected=[Excluded(measure="heat_pump", reason="noise")]),
}


@pytest.fixture(autouse=True)
def _memory_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_DIR", tmp_path)


@pytest.mark.parametrize("pid", list(sh.HOMES))
@pytest.mark.parametrize("persona", list(PERSONAS))
def test_template_passes_checker_for_every_persona_and_home(pid, persona):
    res = advise(pid, sh.run, context=PERSONAS[persona], use_llm=False)
    assert res.explanation.source == "template"
    sheet = build_factsheet({**canonical(res.scenario), "decision": res.decision.facts})
    draft = template_report(sheet)
    assert check(draft, sheet) == [], (pid, persona)
    assert check_rendered(render(draft, sheet), sheet.scenario_id) == []


def test_tenant_needs_landlord_consent_and_plan_says_so():
    res = advise("syn-poor-semi", sh.run, context=PERSONAS["tenant_short"], use_llm=False)
    assert all(p.status in ("conditional", "not_feasible") for p in res.decision.permissions.values())
    assert "check first with your landlord" in res.explanation.rendered.all_text
    assert "landlord" in res.decision.facts["who_benefits"]


def test_flat_roof_and_listed_rules():
    flat = permissions(canonical(sh.run("syn-flat-mid")), UserContext())
    assert flat["solar_pv"].status in ("not_feasible", "conditional")
    listed = permissions(canonical(sh.run("syn-poor-semi")), UserContext(constraints=["listed_or_conservation"]))
    assert listed["double_glazing"].status == "conditional" and "planning" in listed["double_glazing"].note


def test_plan_respects_budget_and_exclusions():
    _, d = decide(sh.run("syn-poor-semi"), PERSONAS["owner_budget"], sh.run)
    assert d.facts["budget_fit_status"] == "within"
    res, d = decide(sh.run("syn-poor-semi"), PERSONAS["memory"], sh.run)
    applied = canonical(res)["selected_measures"]
    assert "loft_insulation" not in applied and "heat_pump" not in applied
    _, d = decide(sh.run("syn-poor-semi"), UserContext(budget_gbp=10), sh.run)
    assert d.measures == [] and d.choice_code == "budget_none"


def test_empty_context_keeps_engine_default():
    base = sh.run("syn-poor-semi")
    res, d = decide(base, UserContext(), sh.run)
    assert d.measures is None and res is base


@pytest.mark.parametrize("q,expect", [
    ("I'm a tenant and we're moving next year", {"role": "tenant", "horizon": "lt2"}),
    ("my budget is £3,000", {"budget_gbp": 3000}),
    ("budget of 5k", {"budget_gbp": 5000}),
    ("I already did the loft insulation", {"completed": ["loft_insulation"]}),
    ("I don't want solar panels", {"rejected": ["solar_pv"]}),
    ("it's a listed building", {"constraints": ["listed_or_conservation"]}),
    ("What if I add a heat pump?", {}),
    ("Budget of £8,000. We already did the loft insulation, and we don't want a heat pump",
     {"budget_gbp": 8000, "completed": ["loft_insulation"], "rejected": ["heat_pump"]}),
])
def test_keyword_context(q, expect):
    assert keyword_context(q) == expect


def test_memory_sessions_change_plan_and_explain_why():
    cid = "cust-1"
    first = advise("syn-poor-semi", sh.run, customer_id=cid, use_llm=False)
    second = advise_whatif("syn-poor-semi", "my budget is £3,000", sh.run, customer_id=cid, use_llm=False)
    third = advise_whatif("syn-poor-semi", "I already did the loft insulation", sh.run, customer_id=cid, use_llm=False)
    plans = [canonical(r.scenario)["selected_measures"] for r in (first, second, third)]
    assert plans[0] != plans[1] != plans[2] and "loft_insulation" not in plans[2]
    assert second.updated_context and "budget" in " ".join(second.changes["changes_summary"])
    text = third.explanation.rendered.all_text
    assert "Since last time" in text and "already done" in text
    assert len(memory.load(cid).records) == 3


def test_memory_rejects_unsafe_ids():
    with pytest.raises(ValueError):
        memory.load("../etc/passwd")


@pytest.mark.parametrize("text,code", [
    ("You are allowed to install cavity wall insulation.", "PERMISSION"),
    ("Cavity wall insulation will pay for itself quickly.", "NOT_ASSESSED"),
    ("This plan is within your budget.", "BUDGET"),
    ("You can't afford a heat pump.", "PRIVACY"),
])
def test_context_rules(text, code):
    res = advise("syn-poor-semi", sh.run, context=PERSONAS["tenant_short"], use_llm=False)
    sheet = build_factsheet({**canonical(res.scenario), "decision": res.decision.facts})
    draft = template_report(sheet)
    bad = ExplanationDraft(claims=[*draft.claims, Claim(section="fit", type="statement", text=text)])
    assert code in {e.code for e in check(bad, sheet)}


def test_budget_stated_in_words_survives_an_llm_reading_that_missed_it():
    """eval q40: the LLM parse missed '£5,000'; the keyword reading of the stated budget is kept."""
    from backend.app.llm.claims import WhatIfParse
    from helpers import FakeLLM
    missed = WhatIfParse(kind="question_about_current", add=[], remove=[], unsupported=[])
    res = advise_whatif("syn-poor-semi", "My budget is £5,000. What should I do?", sh.run, use_llm=True,
                        client=FakeLLM(missed))
    assert res.updated_context and res.context.budget_gbp == 5000
    assert "budget" in res.explanation.rendered.all_text.lower()
