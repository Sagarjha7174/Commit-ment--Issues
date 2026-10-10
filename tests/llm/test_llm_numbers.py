"""Number checker: every number in the final answer matches an engine value; retry once, then template."""
import pytest

import fake_engine as fe
from backend.app.llm import explain as E
from backend.app.llm.numbers import NumberCheck, check_numbers, extract_numbers
from backend.app.llm.render import render
from helpers import FakeLLM, as_text, template_for

POOR = "york-demo-poor-semi"


def test_extract_ignores_codes_glued_to_letters():
    assert extract_numbers("CO2 fell; P10 to P90; D20 rule; m² area") == []
    assert extract_numbers("falls by 1,500 kWh/year, £14,500 and 3.1 tonnes, 57%") == ["1,500", "14,500", "3.1", "57"]


@pytest.mark.parametrize("pid", list(fe.HOMES))
def test_template_answers_are_fully_grounded(pid):
    sheet, draft = template_for(pid)
    nc = check_numbers(render(draft, sheet).all_text, sheet)
    assert nc.grounded, nc.unmatched


def test_invented_number_is_caught():
    sheet, draft = template_for(POOR)
    text = render(draft, sheet).all_text + " Gas use is estimated to fall by 12,345 kWh/year."
    nc = check_numbers(text, sheet)
    assert not nc.grounded and nc.unmatched == ["12,345"] and nc.matched == nc.total - 1


def test_display_roundings_are_accepted():
    sheet, _ = template_for(POOR)
    sheet.payload_values.update({"package.carbon_saving_kg": 3120.41, "package.bill_saving_gbp": 389.83,
                                 "uncertainty.prob_bill_falls": 0.9979, "package.gas_saving_kwh": 20957.36})
    nc = check_numbers("3.1 tonnes, £390, 100%, 20,960 kWh/year and 21,000 kWh", sheet)
    assert nc.grounded, nc.unmatched


def _ungrounded_then(results):
    """Patch check_numbers so the first calls fail (one unsupported number) and later ones pass."""
    seq = list(results)

    def fake(text, sheet, extra=()):
        ok = seq.pop(0) if seq else True
        return NumberCheck(total=3, matched=3 if ok else 2, unmatched=[] if ok else ["999"])
    return fake


def test_unsupported_number_regenerates_once_with_feedback(monkeypatch):
    sheet, draft = template_for(POOR)
    text = as_text(draft)
    monkeypatch.setattr(E, "check_numbers", _ungrounded_then([False, True]))
    llm = FakeLLM(text, text)
    res = E.explain_sheet(sheet, client=llm)
    assert res.number_retry and res.source in ("llm", "llm_patched") and len(llm.calls) == 2
    assert '"999"' in llm.calls[1]["user"] and res.number_check.grounded


def test_unsupported_number_twice_falls_back_to_template(monkeypatch):
    sheet, draft = template_for(POOR)
    text = as_text(draft)
    monkeypatch.setattr(E, "check_numbers", _ungrounded_then([False, False, True]))
    res = E.explain_sheet(sheet, client=FakeLLM(text, text))
    assert res.source == "template" and "unsupported numbers" in res.fallback_reason
    assert res.number_check.grounded


def test_failed_provider_falls_back_to_template():
    sheet, _ = template_for(POOR)
    res = E.explain_sheet(sheet, client=FakeLLM())   # no answers queued: provider unavailable
    assert res.source == "template" and res.fallback_reason.startswith("llm unavailable")
    assert res.number_check is not None and res.number_check.grounded
