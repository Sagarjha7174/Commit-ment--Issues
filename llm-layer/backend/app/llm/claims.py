"""Schemas shared by the LLM, the templates and the checker.

The LLM writes short plain-English prose per section (ExplanationText /
WhatIfText), with numbers only as placeholders such as
{energy_results.change.gas_saving_kwh}. Code splits that prose into one Claim
per sentence and infers each claim's type and measures from the fact values and
wording (extract.py), so the LLM never has to label anything. Templates build
Claims directly. The checker works on Claims either way.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .measures import MeasureId

Section = Literal[
    "fit",           # for you: situation, why this plan, who pays and who benefits, budget (decision context)
    "score",         # score, class and why
    "issues",        # key issues pulling the score down
    "plan",          # recommended measures, in order
    "energy",        # gas and electricity changes, separately
    "carbon",        # carbon change
    "cost",          # package cost, bills
    "value",         # property value (indicative) or why it is not estimated
    "not_suitable",  # infeasible / needs-verification measures and why
    "next_steps",    # before you start: consents, checks, who to ask (decision context)
    "caveats",       # warnings, assumptions, provenance
    "whatif",        # what changed versus the previous scenario
]

SECTION_ORDER: tuple[str, ...] = (
    "fit", "score", "issues", "plan", "energy", "carbon", "cost", "value", "not_suitable", "next_steps", "caveats",
    "whatif",
)

SECTION_TITLES: dict[str, str] = {
    "fit": "For you",
    "score": "Your Green Home Score",
    "issues": "What is holding the score back",
    "plan": "Recommended improvements",
    "energy": "Energy savings",
    "carbon": "Carbon",
    "cost": "Cost",
    "value": "Property value",
    "not_suitable": "Not suitable or needs checking",
    "next_steps": "Before you start",
    "caveats": "Things to know",
    "whatif": "What changed",
}

ClaimType = Literal[
    "statement",       # neutral fact about the home or result
    "recommendation",  # proposes a selected, feasible measure
    "saving",          # reports a reduction
    "increase",        # reports a rise
    "feasibility",     # why a measure is infeasible or needs verification
    "missing_data",    # something is unavailable / not estimated, and why
    "caveat",          # estimates, assumptions, warnings, provenance
    "out_of_scope",    # the system cannot answer this
]


class Claim(BaseModel):
    """One sentence (or two closely linked ones) of an explanation."""

    section: Section
    type: ClaimType
    text: str
    keys: list[str] = Field(default_factory=list)          # placeholders count automatically
    measures: list[MeasureId] = Field(default_factory=list)  # mentions are also detected from the text


class ExplanationDraft(BaseModel):
    """Claims ready to check and render."""

    claims: list[Claim]


_SECTION_HELP = "Plain-English sentences for the homeowner, numbers only as {placeholders}. Empty string if nothing applies."


class ExplanationText(BaseModel):
    """What the LLM returns in report mode: prose per section."""

    score: str = Field(description=_SECTION_HELP)
    issues: str = Field(description=_SECTION_HELP)
    plan: str = Field(description=_SECTION_HELP)
    energy: str = Field(description=_SECTION_HELP)
    carbon: str = Field(description=_SECTION_HELP)
    cost: str = Field(description=_SECTION_HELP)
    value: str = Field(description=_SECTION_HELP)
    not_suitable: str = Field(description=_SECTION_HELP)
    caveats: str = Field(description=_SECTION_HELP)
    fit: str = Field(default="", description="Only when a DECISION CONTEXT is given: the situation, why this plan, "
                                              "who pays and who benefits, budget. " + _SECTION_HELP)
    next_steps: str = Field(default="", description="Only when a DECISION CONTEXT is given: consents and checks "
                                                     "before starting, and who to ask. " + _SECTION_HELP)


class WhatIfText(BaseModel):
    """What the LLM returns in what-if mode."""

    whatif: str = Field(description=_SECTION_HELP)


class WhatIfParse(BaseModel):
    """The LLM's reading of a free-text what-if question. Validated by code before use."""

    kind: Literal["change_measures", "question_about_current", "out_of_scope", "update_context"]
    add: list[MeasureId] = Field(description="Measures the user wants added to the scenario")
    remove: list[MeasureId] = Field(description="Measures the user wants removed from the scenario")
    role: Optional[Literal["tenant", "owner_occupier", "landlord", "selling"]] = Field(
        default=None, description="Only if the user states their role")
    horizon: Optional[Literal["lt2", "y2_5", "y5_10", "y10_plus", "uncertain"]] = Field(
        default=None, description="Only if the user states how long they expect to stay")
    budget_gbp: Optional[int] = Field(default=None, description="Only if the user states an upfront budget, in pounds")
    priorities: list[Literal["lower_bills", "carbon", "low_upfront_cost", "comfort"]] = Field(
        default_factory=list, description="Only priorities the user states")
    constraints: list[Literal["no_roof_access", "listed_or_conservation", "cannot_alter_exterior", "shared_building"]] = \
        Field(default_factory=list, description="Only constraints the user states")
    completed: list[MeasureId] = Field(default_factory=list, description="Measures the user says are already done")
    rejected: list[MeasureId] = Field(default_factory=list, description="Measures the user says they do not want")
    unsupported: list[str] = Field(
        description="Short descriptions of anything requested that is not a supported measure change"
    )
