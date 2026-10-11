"""Fill {placeholders} with formatted values from the fact sheet.

Only this module turns facts into displayed numbers, so units, rounding and
sign handling are identical everywhere (LLM output, templates, what-ifs).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .claims import SECTION_ORDER, SECTION_TITLES, Claim, ExplanationDraft
from .facts_view import SAVING_KINDS, UP_KINDS, Fact, FactSheet

# {path}, {path|abs}, or a direction-carrying filter on a change: {path|change} -> "fall by 1,500 kWh/year",
# {path|changes} -> "falls by 1,500 kWh/year" (or rise / not change). Paths are lower-case dotted keys.
PLACEHOLDER_RE = re.compile(r"\{([a-z0-9_]+(?:\.[a-z0-9_]+)*)(?:\|(abs|change|changes))?\}")
DIRECTION_FILTERS = ("change", "changes")


def placeholders(text: str) -> list[tuple[str, bool]]:
    """(key, uses_abs) for every placeholder in the text, in order."""
    return [(m.group(1), m.group(2) is not None) for m in PLACEHOLDER_RE.finditer(text)]


def strip_placeholders(text: str) -> str:
    return PLACEHOLDER_RE.sub(" ", text)


def _round_kwh(v: float) -> int:
    return int(round(v, -1)) if abs(v) >= 1000 else int(round(v))


def _num(v: float) -> str:
    if float(v).is_integer():
        return f"{int(v):,}"
    return f"{v:,.1f}"


def format_change(fact: Fact, third_person: bool) -> str:
    """'fall by X' / 'rise by X' / 'not change' (or 'falls by X' / 'rises by X' / 'does not change')."""
    size = format_fact(fact)
    if not fact.available:
        return size
    v = float(fact.value)
    if v == 0:
        return "does not change" if third_person else "not change"
    if fact.kind in SAVING_KINDS:
        verb = "fall" if v > 0 else "rise"
    else:  # up-kinds: score points, extra cost
        verb = "go up" if v > 0 else "go down"
    if third_person:
        verb = {"fall": "falls", "rise": "rises", "go up": "goes up", "go down": "goes down"}[verb]
    return f"{verb} by {size}"


def format_fact(fact: Fact, use_abs: bool = False) -> str:
    """Human-readable value with its unit. Unavailable values are never shown as 0."""
    if not fact.available:
        return {
            "not_estimated": "not estimated",
            "needs_verification": "needs verification",
        }.get(fact.status, "not available")

    v = fact.value
    k = fact.kind
    if k == "bool":
        return "yes" if v else "no"
    if k == "text":
        return str(v)
    if k == "text_list":
        items = [str(x) for x in v]
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
    if k == "score_range":
        lo, hi = v
        return f"{int(round(lo))}–{int(round(hi))}"

    x = float(v)
    if use_abs or k in SAVING_KINDS or k in UP_KINDS:
        # Changes are shown as sizes; the sentence's wording carries the direction (checked by the checker).
        x = abs(x)
    sign = "-" if x < 0 else ""
    a = abs(x)
    if k in ("kwh", "kwh_change"):
        return f"{sign}{_round_kwh(a):,} kWh/year"
    if k in ("kg", "kg_change"):
        if a >= 1000:
            return f"{sign}{a / 1000:.1f} tonnes CO2e/year"
        return f"{sign}{int(round(a)):,} kg CO2e/year"
    if k in ("gbp", "gbp_change", "gbp_saving"):
        return f"{sign}£{int(round(a)):,}"
    if k == "years":
        return f"{sign}{_num(round(a, 1))} years"
    if k == "share":
        return f"{int(round(a * 100))}%"
    if k == "pct":
        return f"{sign}{a:.1f}%" if a < 10 else f"{sign}{int(round(a))}%"
    if k == "weight":
        return f"{int(round(a * 100))}%"
    if k == "score":
        return f"{sign}{int(round(a))}/100"
    if k == "points":
        return f"{sign}{a:.1f} points"
    if k == "score_change":
        return f"{int(round(a))} points"
    if k == "area":
        return f"{int(round(a)):,} m²"
    return f"{sign}{_num(a)}"


@dataclass
class Span:
    """One filled-in number, so the UI can show 'Why this number?'."""

    key: str
    display: str
    status: str
    provenance: str | None
    direction: str | None = None  # "reduction" / "increase" / "up" / "down" / "no change" (arithmetic direction)
    sentiment: str | None = None  # "good" / "bad" / "neutral" for the homeowner: what the UI colours by


@dataclass
class RenderedClaim:
    section: str
    type: str
    template: str
    text: str
    keys: list[str]
    measures: list[str]
    spans: list[Span] = field(default_factory=list)


@dataclass
class RenderedSection:
    id: str
    title: str
    claims: list[RenderedClaim]


@dataclass
class RenderedExplanation:
    scenario_id: str
    property_id: str | None
    sections: list[RenderedSection]

    @property
    def markdown(self) -> str:
        lines: list[str] = []
        for s in self.sections:
            lines.append(f"**{s.title}**")
            lines.append(" ".join(c.text for c in s.claims))
            lines.append("")
        return "\n".join(lines).strip()

    @property
    def all_text(self) -> str:
        return "\n".join(c.text for s in self.sections for c in s.claims)


def render_claim(claim: Claim, sheet: FactSheet) -> RenderedClaim:
    spans: list[Span] = []

    def fill(m: re.Match[str]) -> str:
        key, filt = m.group(1), m.group(2)
        fact = sheet.get(key)
        if fact is None:  # the checker rejects this before rendering; never print a raw key
            raise KeyError(key)
        shown = (format_change(fact, filt == "changes") if filt in DIRECTION_FILTERS and fact.signed
                 else format_fact(fact, filt == "abs"))
        spans.append(Span(key, shown, fact.status, fact.provenance, fact.direction, fact.sentiment))
        return shown

    text = PLACEHOLDER_RE.sub(fill, claim.text)
    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)  # a filled value ending in "." before the sentence's own "."
    if text[:1].islower():
        text = text[0].upper() + text[1:]
    text = text.rstrip()
    if text and text[-1] not in ".!?":   # every rendered sentence ends with a full stop (a cited warning may not)
        text += "."
    return RenderedClaim(claim.section, claim.type, claim.text, text, list(claim.keys), list(claim.measures), spans)


def render(draft: ExplanationDraft, sheet: FactSheet) -> RenderedExplanation:
    by_section: dict[str, list[RenderedClaim]] = {}
    for c in draft.claims:
        by_section.setdefault(c.section, []).append(render_claim(c, sheet))
    sections = [RenderedSection(s, SECTION_TITLES[s], by_section[s]) for s in SECTION_ORDER if s in by_section]
    return RenderedExplanation(sheet.scenario_id, sheet.property_id, sections)


def to_dict(r: RenderedExplanation) -> dict[str, Any]:
    """JSON-ready form for the FastAPI response."""
    return {
        "scenario_id": r.scenario_id,
        "property_id": r.property_id,
        "markdown": r.markdown,
        "sections": [
            {
                "id": s.id,
                "title": s.title,
                "claims": [
                    {
                        "type": c.type,
                        "text": c.text,
                        "keys": c.keys,
                        "measures": c.measures,
                        "spans": [vars(sp) for sp in c.spans],
                    }
                    for c in s.claims
                ],
            }
            for s in r.sections
        ],
    }
