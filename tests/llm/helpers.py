"""Shared helpers for the LLM-layer tests."""

from __future__ import annotations

import itertools
from collections import deque

import fake_engine as fe
from backend.app.llm.claims import SECTION_ORDER, Claim, ExplanationDraft, ExplanationText, WhatIfText
from backend.app.llm.client import LLMResult, LLMSettings, LLMUnavailable
from backend.app.llm.facts_view import build_factsheet
from backend.app.llm.templates import template_report


def sheet_for(pid: str, measures: list[str] | None = None):
    return build_factsheet(fe.run(pid, measures))


def template_for(pid: str, measures: list[str] | None = None):
    sheet = sheet_for(pid, measures)
    return sheet, template_report(sheet)


def replace_claim(draft: ExplanationDraft, index: int, **changes) -> ExplanationDraft:
    claims = list(draft.claims)
    claims[index] = claims[index].model_copy(update=changes)
    return ExplanationDraft(claims=claims)


def add_claim(draft: ExplanationDraft, **fields) -> ExplanationDraft:
    base = {"keys": [], "measures": [], "relation": None}
    return ExplanationDraft(claims=[*draft.claims, Claim(**{**base, **fields})])


def drop_claims(draft: ExplanationDraft, pred) -> ExplanationDraft:
    return ExplanationDraft(claims=[c for c in draft.claims if not pred(c)])


def find(draft: ExplanationDraft, pred) -> int:
    return next(i for i, c in enumerate(draft.claims) if pred(c))


def as_text(draft: ExplanationDraft, mode: str = "report"):
    """The prose an LLM would return for these claims (one paragraph per section)."""
    paras = {s: " ".join(c.text for c in draft.claims if c.section == s) for s in SECTION_ORDER}
    if mode == "whatif":
        return WhatIfText(whatif=paras["whatif"])
    return ExplanationText(**{s: paras[s] for s in ExplanationText.model_fields})


def all_measure_sets(pid: str):
    """Every subset of feasible + needs-verification measures for a home (at most 128)."""
    home = fe.HOMES[pid]
    usable = [m for m, v in home["feasibility"].items()
              if (v if isinstance(v, str) else v["state"]) != "infeasible"]
    for r in range(len(usable) + 1):
        for combo in itertools.combinations(usable, r):
            yield list(combo)


class FakeLLM:
    """Stands in for LLMClient: returns queued answers, or raises queued exceptions."""

    def __init__(self, *answers):
        self.settings = LLMSettings(providers=("fake",), enabled=True, use_cache=False)
        self.queue = deque(answers)
        self.calls: list[dict] = []

    def structured(self, **kwargs):
        self.calls.append(kwargs)
        if not self.queue:
            raise LLMUnavailable("exhausted", "no more fake answers")
        nxt = self.queue.popleft()
        if isinstance(nxt, Exception):
            raise nxt
        return LLMResult(nxt, "fake-model", False, 1, {"input_tokens": 1, "output_tokens": 1}, provider="fake")
