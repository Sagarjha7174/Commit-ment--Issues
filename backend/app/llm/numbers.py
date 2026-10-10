"""Number checker: every number in a final answer must match an engine value.

Explanations are grounded by construction (the LLM writes placeholders; render.py fills them), and this module is the
independent check on the final text. A number matches when it equals an engine value (payload or fact sheet), its
absolute value, x100 (a share shown as a percentage) or /1000 (kg shown as tonnes), at 0-2 decimals or rounded to the
nearest 10 / 100 / 1,000 (display rounding for kWh and pounds). Numbers inside engine-written text facts (reasons,
warnings, age bands) count as engine values. Codes glued to letters (CO2, P10, D20) are not numbers.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable

from .facts_view import FactSheet

log = logging.getLogger("llm.numbers")

NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.,])\d[\d,]*(?:\.\d+)?(?![A-Za-z0-9])")
_TEXT_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


@dataclass
class NumberCheck:
    total: int
    matched: int
    unmatched: list[str] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        return not self.unmatched

    @property
    def share_matched(self) -> float:
        return 1.0 if self.total == 0 else self.matched / self.total

    def to_dict(self) -> dict:
        return {**asdict(self), "grounded": self.grounded, "share_matched": round(self.share_matched, 4)}


def _parse(token: str) -> float | None:
    t = token.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _forms(v: float) -> set[float]:
    """Every display form of an engine value."""
    out = set()
    for u in {abs(v), abs(v) * 100, abs(v) / 1000}:
        for d in (0, 1, 2):
            out.add(round(round(u, d), 6))
        if u >= 100:
            out.update(round(round(u, k), 6) for k in (-1, -2, -3))
    return out


def allowed_values(sheet: FactSheet, extra: Iterable[float] = ()) -> set[float]:
    vals: list[float] = list(sheet.payload_values.values()) + list(extra)
    for f in sheet.facts.values():
        if not f.available:
            continue
        if f.numeric:
            if isinstance(f.value, (tuple, list)):
                vals += [float(x) for x in f.value if isinstance(x, (int, float))]
            elif isinstance(f.value, (int, float)) and not isinstance(f.value, bool):
                vals.append(float(f.value))
        elif f.kind in ("text", "text_list"):
            text = " ".join(map(str, f.value)) if isinstance(f.value, (list, tuple)) else str(f.value)
            vals += [x for x in (_parse(t) for t in _TEXT_NUMBER_RE.findall(text)) if x is not None]
    out: set[float] = set()
    for v in vals:
        out |= _forms(float(v))
    return out


def extract_numbers(text: str) -> list[str]:
    return NUMBER_RE.findall(text)


def check_numbers(text: str, sheet: FactSheet, extra: Iterable[float] = ()) -> NumberCheck:
    allowed = allowed_values(sheet, extra)
    tokens = extract_numbers(text)
    unmatched = []
    for t in tokens:
        x = _parse(t)
        if x is None or round(x, 6) not in allowed:
            unmatched.append(t)
    return NumberCheck(total=len(tokens), matched=len(tokens) - len(unmatched), unmatched=unmatched)


def log_check(scenario_id: str, source: str, nc: NumberCheck) -> None:
    log.info(json.dumps({"scenario_id": scenario_id, "source": source, "numbers": nc.total,
                         "grounded": nc.matched, "unsupported": len(nc.unmatched)}))
