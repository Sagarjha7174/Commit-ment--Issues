"""Turn the LLM's section prose into checkable claims: one claim per sentence.

The LLM only writes text. Code decides what each sentence is (saving, increase,
missing data, feasibility, recommendation, caveat, statement) from the fact
values and the wording, and which measures it refers to. That is more reliable
than asking the model to label its own sentences, and it keeps the output
format simple enough for small local models.
"""

from __future__ import annotations

import re

from .checker import (MISSING_WORDS, UNSUITABLE_WORDS, Mode, claim_measures)
from .claims import SECTION_ORDER, Claim, ClaimType, ExplanationDraft, ExplanationText, WhatIfText
from .facts_view import SAVING_KINDS, FactSheet
from .render import placeholders

_ABBREV = re.compile(r"\b(e\.g|i\.e|etc|approx|vs)\.", re.IGNORECASE)
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z{(\"'])")


def split_sentences(text: str) -> list[str]:
    """Placeholder-safe sentence split (keys contain dots but never spaces)."""
    protected = _ABBREV.sub(lambda m: m.group(0).replace(".", "․"), text.strip())
    parts = [p.strip().replace("․", ".") for p in _SPLIT.split(protected)]
    return [p for p in parts if p]


def infer_type(section: str, text: str, sheet: FactSheet, measures: set[str]) -> ClaimType:
    nonfeasible = {m for m in measures if sheet.feasibility.get(m) and sheet.feasibility[m].state != "feasible"}
    if measures and (section == "not_suitable" or (nonfeasible and UNSUITABLE_WORDS.search(text))):
        return "feasibility"
    used = placeholders(text)
    facts = [sheet.get(k) for k, _ in used]
    if any(f is not None and not f.available for f in facts) or MISSING_WORDS.search(text):
        return "missing_data"
    signed = [float(f.value) for f in facts if f is not None and f.available and f.kind in SAVING_KINDS
              and float(f.value) != 0]
    if signed:
        return "increase" if all(v < 0 for v in signed) else "saving"
    if section == "plan" and measures:
        return "recommendation"
    if section == "caveats":
        return "caveat"
    return "statement"


def extract_claims(output: ExplanationText | WhatIfText | dict, sheet: FactSheet, mode: Mode = "report") \
        -> ExplanationDraft:
    data = output.model_dump() if hasattr(output, "model_dump") else dict(output)
    claims: list[Claim] = []
    for section in SECTION_ORDER:
        text = data.get(section)
        if not isinstance(text, str) or not text.strip():
            continue
        for sentence in split_sentences(text):
            probe = Claim(section=section, type="statement", text=sentence)
            measures = claim_measures(probe, sheet)
            ctype = infer_type(section, sentence, sheet, measures)
            claims.append(Claim(section=section, type=ctype, text=sentence, measures=sorted(measures)))
    return ExplanationDraft(claims=claims)
