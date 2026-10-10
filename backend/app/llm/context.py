"""Decision context: who is deciding, for how long, with what constraints, and what they already did or refused.

Everything here is deterministic code. It turns an optional, privacy-first UserContext into:
  - a permission overlay per measure (the product concept's statuses: not feasible / unverified / conditional /
    ruled out by you / no known permission needed; never "confirmed", because we cannot verify law),
  - a plan chosen from the engine's own package search (budget, priorities, horizon, role, exclusions),
  - plain-English facts the LLM cites by placeholder (who pays and who benefits, next steps, what is not assessed).
The LLM never decides any of this; it explains it. Numbers still come only from the engine.

Scope (docs: narrow, verifiable, UK): no climate, occupancy or legal verification (bills and payback come from the engine). Those are
reported as "not assessed".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field

from .measures import MEASURE_ORDER, MeasureId, display_name, ordered

Role = Literal["tenant", "owner_occupier", "landlord", "selling", "unknown"]
Horizon = Literal["lt2", "y2_5", "y5_10", "y10_plus", "uncertain"]
Priority = Literal["lower_bills", "carbon", "low_upfront_cost", "comfort"]
Constraint = Literal["no_roof_access", "listed_or_conservation", "cannot_alter_exterior", "shared_building"]
PermissionStatus = Literal["not_feasible", "unverified", "conditional", "ruled_out_by_you", "no_known_permission_needed"]

ROLE_TEXT = {"tenant": "a tenant", "owner_occupier": "an owner-occupier", "landlord": "a landlord",
             "selling": "an owner preparing to sell", "unknown": ""}
HORIZON_TEXT = {"lt2": "expecting to stay less than two years", "y2_5": "expecting to stay two to five years",
                "y5_10": "expecting to stay five to ten years", "y10_plus": "expecting to stay more than ten years",
                "uncertain": ""}
EXTERIOR = {"solid_wall", "solar_pv", "double_glazing"}   # change the outside of the building
ROOF = {"solar_pv", "loft_insulation"}
NOT_ASSESSED = ("local climate and weather risks, occupancy and appliance changes, installer quotes, and whether any "
                "permission will actually be granted (bills use capped prices, not your tariff)")


class Excluded(BaseModel):
    measure: MeasureId
    reason: str = Field(default="", max_length=120)


class UserContext(BaseModel):
    """All optional. Bands and choices only: never salary, employer, or anything inferred about the person."""

    role: Role = "unknown"
    horizon: Horizon = "uncertain"
    priorities: list[Priority] = Field(default_factory=list)
    budget_gbp: Optional[int] = Field(default=None, ge=0, le=250_000, description="upper bound the user chose")
    constraints: list[Constraint] = Field(default_factory=list)
    completed: list[MeasureId] = Field(default_factory=list)
    rejected: list[Excluded] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return self == UserContext()

    def excluded(self) -> set[str]:
        return set(self.completed) | {r.measure for r in self.rejected}


@dataclass
class Permission:
    status: PermissionStatus
    who: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class Decision:
    measures: Optional[list[str]]           # None = engine default (every feasible measure)
    choice_code: str
    choice_text: str
    permissions: dict[str, Permission]
    facts: dict[str, Any]                   # goes into the scenario contract under "decision"


def _is_flat(contract: dict) -> bool:
    t = str((contract.get("inputs") or {}).get("type") or "")
    return "Flat" in t or "Maisonette" in t


def _pre_1919(contract: dict) -> bool:
    band = str((contract.get("inputs") or {}).get("age_band") or "")
    m = re.search(r"(\d{4})\s*$", band) or re.search(r"(\d{4})", band)
    return ("before" in band.lower()) or bool(m and int(m.group(1)) <= 1919)


def permissions(contract: dict, ctx: UserContext) -> dict[str, Permission]:
    """The product concept's permission statuses, layered on the engine's physical feasibility.
    `contract` is the canonical scenario (facts_view.canonical)."""
    feas = {m: (v if isinstance(v, dict) else {"state": v}) for m, v in (contract.get("feasibility") or {}).items()}
    out: dict[str, Permission] = {}
    for m in MEASURE_ORDER:
        f = feas.get(m)
        state = f.get("state", "needs_verification") if f else "needs_verification"
        if state == "infeasible":
            out[m] = Permission("not_feasible", note=(f or {}).get("reason") or "a known constraint rules it out")
            continue
        if m in ctx.excluded():
            why = "you told us it is already done" if m in ctx.completed else "you told us you do not want it"
            out[m] = Permission("ruled_out_by_you", note=why)
            continue
        if "cannot_alter_exterior" in ctx.constraints and m in EXTERIOR:
            out[m] = Permission("ruled_out_by_you", note="you told us the outside of the building cannot be changed")
            continue
        who: list[str] = []
        notes: list[str] = []
        if ctx.role == "tenant":
            who.append("your landlord")
            notes.append("ask your landlord for written consent" if m != "smart_thermostat" else
                         "ask your landlord before changing the heating controls")
        if (_is_flat(contract) or "shared_building" in ctx.constraints) and m in (ROOF | {"solid_wall"}):
            who.append("the building owner or managing agent")
            notes.append("check with the building owner or managing agent, because the roof or outside walls are shared")
        if "listed_or_conservation" in ctx.constraints and m in EXTERIOR:
            who.append("the local planning authority")
            notes.append("check planning or listed-building consent with the local planning authority")
        if m == "solid_wall" and _pre_1919(contract):
            who.append("a qualified surveyor")
            notes.append("get a damp and moisture assessment from a qualified surveyor first, as the home is older")
        unverified = state == "needs_verification" or ("no_roof_access" in ctx.constraints and m in ROOF)
        if unverified:
            notes.append((f or {}).get("reason") if state == "needs_verification" and f and f.get("reason") else
                         "roof access needs checking first")
        if who:
            out[m] = Permission("conditional", who=who, note="; ".join(n for n in notes if n))
        elif unverified:
            out[m] = Permission("unverified", note="; ".join(n for n in notes if n))
        else:
            out[m] = Permission("no_known_permission_needed")
    return out


def _objective(ctx: UserContext) -> str:
    if ctx.budget_gbp is not None:
        return "budget"
    if "low_upfront_cost" in ctx.priorities or ctx.horizon == "lt2" or ctx.role == "selling":
        return "lowest_cost"
    if ctx.role == "tenant" and not ctx.priorities:
        return "lowest_cost"
    if "carbon" in ctx.priorities:
        return "largest_carbon"
    return "carbon_per_pound"


_CHOICE_TEXT = {
    "budget": "it is the package with the largest estimated carbon saving that fits within your budget of £{budget:,}",
    "budget_none": "no package with an estimated carbon saving fits within your budget of £{budget:,}",
    "lowest_cost": "it is the lowest-cost package that cuts estimated emissions by at least {thr:g}%",
    "largest_carbon": "it is the package with the largest estimated carbon saving",
    "carbon_per_pound": "it saves the most estimated carbon per pound among packages cutting at least {thr:g}%",
    "fallback": "no package meets the selection rule, so the largest estimated saving available is shown",
}


def choose_plan(engine_result: dict, ctx: UserContext, perms: dict[str, Permission]) -> tuple[Optional[list[str]], str]:
    """Pick a package from the engine's own search. Returns (measures, choice code)."""
    search = engine_result.get("packages") or {}
    pkgs = [p for p in search.get("packages") or [] if p.get("status") == "ok" and p.get("confirmed")]
    blocked = {m for m, p in perms.items() if p.status in ("not_feasible", "ruled_out_by_you")}
    pkgs = [p for p in pkgs if not (set(p.get("measures") or []) & blocked)]
    real = [p for p in pkgs if p.get("measures")]
    thr = search.get("threshold_pct") or 0.0
    meets = [p for p in real if (p.get("carbon_saving_pct") or 0) >= thr]
    obj = _objective(ctx)

    def carbon(p): return p.get("carbon_saving_kg") or 0.0
    def cost(p): return p.get("cost_gbp") if p.get("cost_gbp") is not None else float("inf")

    if obj == "budget":
        within = [p for p in real if p.get("cost_gbp") is not None and p["cost_gbp"] <= ctx.budget_gbp and carbon(p) > 0]
        if not within:
            return [], "budget_none"
        best = max(within, key=lambda p: (carbon(p), -cost(p), -len(p["measures"])))
        return ordered(best["measures"]), "budget"
    if not real:
        return [], "fallback"
    if obj == "lowest_cost" and meets:
        best = min(meets, key=lambda p: (cost(p), -carbon(p), len(p["measures"])))
    elif obj == "largest_carbon":
        best = max(real, key=lambda p: (carbon(p), -cost(p)))
    elif obj == "carbon_per_pound" and meets:
        priced = [p for p in meets if cost(p) not in (0, float("inf"))]
        best = max(priced, key=lambda p: (carbon(p) / cost(p), carbon(p))) if priced else max(meets, key=carbon)
    else:
        return ordered(max(real, key=lambda p: (carbon(p), -cost(p)))["measures"]), "fallback"
    return ordered(best["measures"]), obj


def _who_benefits(ctx: UserContext) -> Optional[str]:
    if ctx.role == "tenant":
        return ("the landlord would normally pay for permanent improvements, while you, as the bill payer, would "
                "see most of any energy saving while you live there")
    if ctx.role == "landlord":
        return ("you would pay for the work, while your tenants, who pay the energy bills, would see most of the "
                "energy saving; a better rating may help with lettings rules, but higher rent is not assumed")
    if ctx.role == "selling":
        return ("you would pay for the work, but most of the energy saving after the sale would go to the buyer; "
                "any effect on the sale price is not estimated here")
    if ctx.role == "owner_occupier" and ctx.horizon == "lt2":
        return ("you would pay for the work, but if you move within two years most of the later energy saving would "
                "go to the next occupants")
    return None


def _situation(ctx: UserContext) -> Optional[str]:
    parts = []
    if ctx.role != "unknown":
        parts.append(f"you are {ROLE_TEXT[ctx.role]}")
    if ctx.horizon != "uncertain":
        parts.append(f"you are {HORIZON_TEXT[ctx.horizon]}")
    if ctx.budget_gbp is not None:
        parts.append(f"your budget is up to £{ctx.budget_gbp:,}")
    if ctx.priorities:
        parts.append("you prioritise " + " and ".join(p.replace("_", " ") for p in ctx.priorities))
    if ctx.constraints:
        parts.append("you told us: " + ", ".join(c.replace("_", " ") for c in ctx.constraints))
    return "; ".join(parts) if parts else None


def decide(engine_result: dict, ctx: UserContext, runner: Callable[[str, Optional[list[str]]], dict]) \
        -> tuple[dict, Decision]:
    """Apply the context to an engine result (with packages). Returns (final engine result, decision)."""
    from .facts_view import canonical  # local import: facts_view imports nothing from here

    contract = canonical(engine_result)
    perms = permissions(contract, ctx)
    home_id = contract.get("property_id")
    if ctx.is_empty():
        measures, code = None, "engine_default"
        result = engine_result
    else:
        measures, code = choose_plan(engine_result, ctx, perms)
        result = runner(home_id, measures)
    thr = ((engine_result.get("packages") or {}).get("threshold_pct")) or 10.0
    choice = _CHOICE_TEXT.get(code, "").format(budget=ctx.budget_gbp or 0, thr=thr) if code != "engine_default" else ""

    applied = set(canonical(result).get("selected_measures") or [])
    plan_perms = {m: p for m, p in perms.items() if m in applied}
    steps = []
    for m in ordered(list(applied)):
        p = plan_perms[m]
        if p.status in ("conditional", "unverified") and p.note:
            steps.append(f"{display_name(m)}: {p.note}")
    cost = None
    for p in ((engine_result.get("packages") or {}).get("packages") or []):
        if sorted(p.get("measures") or []) == sorted(applied):
            cost = p.get("cost_gbp")
    budget_status = "not_given" if ctx.budget_gbp is None else (
        "within" if cost is not None and cost <= ctx.budget_gbp else "over" if cost is not None else "unknown")
    budget_text = {"not_given": None,
                   "within": f"the estimated cost is within your budget of up to £{ctx.budget_gbp or 0:,}",
                   "over": f"the estimated cost is above your budget of up to £{ctx.budget_gbp or 0:,}",
                   "unknown": "the cost of this plan could not be compared with your budget"}[budget_status]
    facts: dict[str, Any] = {
        "situation": _situation(ctx),
        "plan_choice": choice or None,
        "who_benefits": _who_benefits(ctx),
        "budget_fit": budget_text,
        "budget_fit_status": budget_status,
        "next_steps": steps or None,
        "not_assessed": NOT_ASSESSED if not ctx.is_empty() else None,
        "completed_note": ("you told us some work is already done; the score still uses the EPC record, which may "
                           "not show it yet") if ctx.completed else None,
        "excluded": [f"{display_name(m)} ({p.note})" for m, p in perms.items() if p.status == "ruled_out_by_you"] or None,
        "permission": {m: {"status": p.status.replace("_", " "), "who": ", ".join(p.who) or None, "note": p.note or None}
                       for m, p in perms.items() if p.status != "not_feasible"},
        "role": ctx.role,
    }
    facts = {k: v for k, v in facts.items() if v is not None}
    return result, Decision(measures, code, choice, perms, facts)
