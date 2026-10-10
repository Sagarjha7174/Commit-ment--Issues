"""Question answering over the engine: the one path used by the API and the evaluation.

Every answer starts from scenario_builder.build(ScenarioRequest) for the selected home. A question about the current
result is answered from the explanation (sections chosen by intent: how green is my home, what should I improve, how
much could I save, could it increase my property value); a question that changes the request goes to the what-if
flow (validated ScenarioRequest, engine rerun, difference explained); anything outside scope is declined with fixed
text. Every answer reports the values it cites (engine values by key) and the number check of its final text.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from typing import Any, Callable, Optional

from .explain import explain_sheet
from .facts_view import FactSheet, build_factsheet
from .numbers import check_numbers, log_check
from .payload import assert_address_free, build_payload
from .whatif import answer_whatif, keyword_parse

INTENTS = (
    ("value", re.compile(r"\b(value|worth|price of (my|the) (home|house)|sell|selling|resale|valuation)\b", re.I),
     ("value", "score")),
    ("save", re.compile(r"\b(save|saving|savings|bill|bills|cost|costs|money|carbon|co2|emissions|energy|kwh|"
                        r"electricity|gas|payback|grant|grants|loan|afford)\b", re.I), ("energy", "carbon", "cost")),
    ("improve", re.compile(r"\b(improve|improvement|recommend|should i|what (can|could|should)|measures?|upgrade|"
                           r"retrofit|first|order|priority)\b", re.I), ("plan", "not_suitable", "issues")),
    ("green", re.compile(r"\b(green|score|rating|epc|efficient|efficiency|how good|how bad)\b", re.I),
     ("score", "issues")),
    ("suitable", re.compile(r"\b(suitable|unsuitable|possible|can i (have|get|fit|install)|why not|missing|unknown|"
                            r"not available|data)\b", re.I), ("not_suitable", "plan", "caveats")),
)
REPORT_RE = re.compile(r"\b(report|explain|summary|summarise|summarize|overview|everything|tell me about my home)\b", re.I)
ALWAYS = ("caveats",)
OUT_OF_SCOPE_TEXT = ("That question is outside what this tool can answer, so nothing was calculated. It can tell you "
                     "how green your home is, what you could improve, how much energy, carbon and money you could "
                     "save, and whether it could affect your property value, and recalculate what-ifs.")
_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_CACHE_MAX = 256


def intents(question: Optional[str]) -> list[str]:
    if not question:
        return []
    return [name for name, rx, _ in INTENTS if rx.search(question)]


def sections_for(question: Optional[str]) -> Optional[list[str]]:
    """Sections that answer the question (None = the full report)."""
    names = intents(question)
    if not names or REPORT_RE.search(question or ""):
        return None
    out: list[str] = []
    for name, _, secs in INTENTS:
        if name in names:
            out += [s for s in secs if s not in out]
    return out + [s for s in ALWAYS if s not in out]


def cited_values(rendered, sheet: FactSheet, sections: Optional[list[str]] = None) -> list[dict]:
    """Every number shown, with its engine value and key ("Why this number?")."""
    out, seen = [], set()
    for sec in rendered.sections:
        if sections and sec.id not in sections:
            continue
        for c in sec.claims:
            for sp in c.spans:
                f = sheet.get(sp.key)
                if f is None or not f.numeric or not f.available or sp.key in seen:
                    continue
                seen.add(sp.key)
                out.append({"key": sp.key, "display": sp.display, "value": f.value, "status": sp.status,
                            "provenance": sp.provenance})
    return out


def _text(rendered, sections: Optional[list[str]]) -> str:
    """The answer text: the sections that answer the question, in the question's order (then caveats)."""
    by_id = {sec.id: sec for sec in rendered.sections}
    order = sections or [sec.id for sec in rendered.sections]
    parts = [f"{by_id[s].title}\n" + " ".join(c.text for c in by_id[s].claims) for s in order if s in by_id]
    return "\n\n".join(parts)


def _key(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _cache_get(k: str) -> Optional[dict]:
    if k in _CACHE:
        _CACHE.move_to_end(k)
        return json.loads(json.dumps(_CACHE[k]))
    return None


def _cache_put(k: str, v: dict) -> None:
    _CACHE[k] = json.loads(json.dumps(v, default=str))
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


def clear_cache() -> None:
    _CACHE.clear()


def explain_question(scenario: dict, question: Optional[str] = None, *, history: Optional[list[dict]] = None,
                     use_llm: bool = True, client=None) -> dict:
    """Answer a question about one engine result. Cached by (scenario_id, question, history, use_llm)."""
    sheet = build_factsheet(scenario)
    k = _key("explain", sheet.scenario_id, (question or "").strip().lower(), history or [], use_llm)
    cached = _cache_get(k)
    if cached is not None:
        return {**cached, "cached": True}
    extra = {"HISTORY": [{"role": h.get("role"), "text": str(h.get("text", ""))[:300]} for h in (history or [])[-4:]]} \
        if history else None
    res = explain_sheet(sheet, use_llm=use_llm, question=question, extra=extra, client=client)
    secs = sections_for(question)
    answer = _text(res.rendered, secs)
    nc = check_numbers(answer, sheet)
    log_check(sheet.scenario_id, res.source, nc)
    out = {"kind": "explain", "answer": answer, "sections": secs or [s.id for s in res.rendered.sections],
           "intents": intents(question), "cited_values": cited_values(res.rendered, sheet, secs),
           "scenario_id": sheet.scenario_id, "grounded": nc.grounded, "numbers": nc.to_dict(),
           "source": res.source, "provider": res.provider, "model": res.model, "fallback_reason": res.fallback_reason,
           "llm_stats": {"llm_sentences": res.llm_sentences, "dropped": len(res.dropped),
                         "template_filled": res.template_filled, "attempts": res.attempts,
                         "number_retry": res.number_retry},
           "recalculated": False, "cached": False}
    _cache_put(k, out)
    return out


def whatif_question(scenario: dict, question: str, runner: Callable, request_runner: Callable, *,
                    use_llm: bool = True, client=None) -> dict:
    ans = answer_whatif(scenario, question, runner, use_llm=use_llm, client=client, request_runner=request_runner)
    answer = ans.explanation.rendered.all_text
    nc = ans.explanation.number_check or check_numbers(answer, ans.sheet)
    o = ans.outcome
    return {"kind": "whatif", "answer": answer, "outcome": o.kind, "recalculated": ans.recalculated,
            "added": o.added, "removed": o.removed, "blocked": o.blocked, "conditional": o.conditional,
            "request_changes": o.request_changes, "refusal_reason": o.invalid_reason,
            "new_request": o.new_request, "previous_scenario_id": build_factsheet(scenario).scenario_id,
            "scenario_id": ans.explanation.scenario_id, "grounded": nc.grounded, "numbers": nc.to_dict(),
            "cited_values": cited_values(ans.explanation.rendered, ans.sheet),
            "source": ans.explanation.source, "parser": o.parser, "scenario": ans.scenario,
            "llm_stats": {"llm_sentences": ans.explanation.llm_sentences, "dropped": len(ans.explanation.dropped),
                          "template_filled": ans.explanation.template_filled, "attempts": ans.explanation.attempts,
                          "number_retry": ans.explanation.number_retry}}


def route(question: Optional[str], current_measures: list[str]) -> str:
    """'explain' | 'whatif' | 'out_of_scope' (keyword reading; the LLM parse runs inside the what-if flow)."""
    if not question:
        return "explain"
    p = keyword_parse(question, current_measures)
    if p.kind in ("change_measures", "change_assumptions"):
        return "whatif"
    if p.kind == "out_of_scope":
        return "out_of_scope"
    if not intents(question) and not REPORT_RE.search(question):
        return "out_of_scope"   # conservative: not about this home's score, plan, savings or value
    return "explain"


def answer(scenario: dict, question: Optional[str], runner: Callable, request_runner: Callable, *,
           history: Optional[list[dict]] = None, use_llm: bool = True, client=None) -> dict:
    """Route a question: explanation, what-if (recalculated by the engine) or a fixed out-of-scope reply."""
    sheet = build_factsheet(scenario)
    r = route(question, sheet.selected_measures)
    if r == "out_of_scope":
        out = {"kind": "out_of_scope", "answer": OUT_OF_SCOPE_TEXT, "cited_values": [], "scenario_id": sheet.scenario_id,
               "grounded": True, "numbers": {"total": 0, "matched": 0, "unmatched": [], "grounded": True},
               "source": "template", "recalculated": False}
    elif r == "whatif":
        out = whatif_question(scenario, question, runner, request_runner, use_llm=use_llm, client=client)
        out.pop("scenario", None)
    else:
        out = explain_question(scenario, question, history=history, use_llm=use_llm, client=client)
    assert_address_free(out)
    return out


def payload_for(scenario: dict) -> dict:
    p = build_payload(scenario)
    assert_address_free(p)
    return p
