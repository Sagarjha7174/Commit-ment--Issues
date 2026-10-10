"""advise(): the decision-context entry point (product concept + Customer Memory extension).

    context (role, horizon, budget, constraints, done / refused measures; optional, from the user or memory)
      -> engine run with the full package search
      -> decide(): permission overlay + plan chosen from the engine's packages -> engine rerun for that plan
      -> decision facts (+ "what changed since last time" from the decision record)
      -> explain_sheet() with the usual checks, patching and template fallback
      -> decision record appended to the customer's memory

A question can also update the context ("I'm a tenant", "my budget is £3,000", "I already did the loft"): the
parser returns kind=update_context, code validates and merges it, and the plan is re-decided and explained.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import memory
from .claims import WhatIfParse
from .client import LLMClient
from .context import Decision, Excluded, UserContext, decide, permissions
from .explain import ExplainResult, explain_sheet
from .facts_view import build_factsheet, canonical
from .measures import measure_mentions, ordered
from .whatif import WhatIfAnswer, answer_whatif, keyword_parse, parse_question

Runner = Callable[[str, Optional[list[str]]], dict]


@dataclass
class AdviceResult:
    scenario: dict
    explanation: ExplainResult
    decision: Decision
    context: UserContext
    changes: Optional[dict[str, Any]] = None
    customer_id: Optional[str] = None
    updated_context: bool = False
    whatif: Optional[WhatIfAnswer] = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {"scenario_id": self.explanation.scenario_id, "scenario": self.scenario,
                "explanation": self.explanation.to_dict(), "context": self.context.model_dump(),
                "plan_choice": self.decision.choice_code, "changes": self.changes,
                "updated_context": self.updated_context, "customer_id": self.customer_id,
                "permissions": {m: {"status": p.status, "who": p.who, "note": p.note}
                                for m, p in self.decision.permissions.items()}}


def advise(home_id: str, runner: Runner, *, context: Optional[UserContext] = None, customer_id: Optional[str] = None,
           use_llm: bool = True, client: Optional[LLMClient] = None, question: Optional[str] = None,
           remember: bool = True) -> AdviceResult:
    profile = memory.load(customer_id) if customer_id else None
    ctx = context if context is not None else (profile.context if profile else UserContext())
    base = runner(home_id, None)
    result, decision = decide(base, ctx, runner)
    contract = canonical(result)
    record = memory.record_from(contract, ctx, decision.choice_code)
    prev = next((r for r in reversed(profile.records) if r.home_id == record.home_id), None) if profile else None
    changes = memory.what_changed(prev, record)
    contract["decision"] = {**decision.facts, **(changes or {})}
    sheet = build_factsheet(contract)
    expl = explain_sheet(sheet, use_llm=use_llm, question=question, client=client)
    if profile is not None and remember:
        profile.context = ctx
        profile.records.append(record)
        memory.save(profile)
    return AdviceResult(result, expl, decision, ctx, changes, customer_id)


# --- Context updates from free text --------------------------------------------------------------------------

_ROLE_RES = [
    (re.compile(r"\b(i'?m|i am) (a |the )?(tenant|renter)\b|\bi rent\b|\b(i'?m|we'?re|i am|we are) renting\b", re.I), "tenant"),
    (re.compile(r"\b(i'?m|i am) (a |the )?landlord\b|\bi let (it|this|the (house|flat|home))( out)?\b", re.I), "landlord"),
    (re.compile(r"\b(i'?m|we'?re|i am|we are) selling\b|\bsell(ing)? (the|my|our|this) (house|home|flat|place)\b|"
                r"\bput (it|the house|the flat) on the market\b", re.I), "selling"),
    (re.compile(r"\bi own (it|the|this|my)\b|\b(i'?m|i am) the owner\b|\bhomeowner\b|\bowner[- ]occupier\b", re.I),
     "owner_occupier"),
]
_SHORT = re.compile(r"\b(mov(e|ing)|leav(e|ing)|sell(ing)?)\b[^.]{0,30}\b(this year|next year|a year|one year|1 year|"
                    r"months?|18 months)\b", re.I)
_MID = re.compile(r"\b(mov(e|ing)|leav(e|ing)|stay(ing)?)\b[^.]{0,30}\b(two|three|four|five|2|3|4|5) years\b", re.I)
_LONG = re.compile(r"\b(long[- ]term|forever|for good|(10|ten|15|fifteen|20|twenty)\+? years|rest of my life)\b", re.I)
_BUDGET = re.compile(r"\bbudget\b[^.£\d]{0,25}£?\s?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\b|"
                     r"£\s?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\b[^.]{0,25}\bbudget\b", re.I)
_DONE = re.compile(r"\b(already (have|has|had|did|done|installed|got|fitted|put in)|i'?ve (already )?(done|installed|"
                   r"got|fitted|put in)|we'?ve (already )?(done|installed|got|fitted|put in))\b", re.I)
_REFUSE = re.compile(r"\b(don'?t|do not|never) want\b|\bnot interested in\b|\brather not\b|\bno thanks to\b", re.I)
_CONSTRAINTS = [
    (re.compile(r"\blisted (building|property|home)\b|\bconservation area\b|\bit'?s listed\b", re.I),
     "listed_or_conservation"),
    (re.compile(r"\b(can'?t|cannot|not allowed to) (change|alter|touch) the (outside|exterior|facade|front)\b", re.I),
     "cannot_alter_exterior"),
    (re.compile(r"\bno (access to the )?roof( access)?\b|\bcan'?t (get|go) (on|to|onto) the roof\b", re.I), "no_roof_access"),
    (re.compile(r"\bshared (building|roof|block)\b|\bblock of flats\b", re.I), "shared_building"),
]


def keyword_context(question: str) -> dict[str, Any]:
    """Offline reading of context statements. Conservative: only clear phrasings."""
    out: dict[str, Any] = {}
    for rx, role in _ROLE_RES:
        if rx.search(question):
            out["role"] = role
            break
    if _SHORT.search(question):
        out["horizon"] = "lt2"
    elif _MID.search(question):
        out["horizon"] = "y2_5"
    elif _LONG.search(question):
        out["horizon"] = "y10_plus"
    m = _BUDGET.search(question)
    if m:
        num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        try:
            val = float(num.replace(",", ""))
            out["budget_gbp"] = int(val * 1000 if unit else val)
        except ValueError:
            pass
    hits = {key: rx.search(question) for rx, key in ((_DONE, "completed"), (_REFUSE, "rejected"))}
    for key, hit in hits.items():
        if hit:  # a statement only claims the measures up to the next statement ("already did X, don't want Y")
            later = [h.start() for k, h in hits.items() if h and k != key and h.start() > hit.start()]
            end = min(later) if later else len(question)
            out[key] = ordered([mm for mm, pos in measure_mentions(question) if hit.start() < pos < end])
    cons = [c for rx, c in _CONSTRAINTS if rx.search(question)]
    if cons:
        out["constraints"] = cons
    return {k: v for k, v in out.items() if v not in (None, [], "")}


def merge_context(ctx: UserContext, parsed: WhatIfParse) -> UserContext:
    """Code validates and merges what the parser read; nothing is inferred beyond what the user said."""
    data = ctx.model_dump()
    if parsed.role:
        data["role"] = parsed.role
    if parsed.horizon:
        data["horizon"] = parsed.horizon
    if parsed.budget_gbp is not None and 0 <= parsed.budget_gbp <= 250_000:
        data["budget_gbp"] = int(parsed.budget_gbp)
    data["priorities"] = sorted(set(data["priorities"]) | set(parsed.priorities))
    data["constraints"] = sorted(set(data["constraints"]) | set(parsed.constraints))
    data["completed"] = ordered(set(data["completed"]) | set(parsed.completed))
    rejected = {r["measure"]: r for r in data["rejected"]}
    for m in parsed.rejected:
        rejected.setdefault(m, {"measure": m, "reason": "said in conversation"})
    for m in parsed.completed:
        rejected.pop(m, None)
    data["rejected"] = [Excluded(**r) for r in rejected.values()]
    return UserContext(**data)


def _has_context(p: WhatIfParse) -> bool:
    return bool(p.role or p.horizon or p.budget_gbp is not None or p.priorities or p.constraints or p.completed
                or p.rejected)


def advise_whatif(home_id: str, question: str, runner: Runner, *, customer_id: Optional[str] = None,
                  context: Optional[UserContext] = None, use_llm: bool = True,
                  client: Optional[LLMClient] = None) -> AdviceResult:
    """A question in the context of the user's situation: either it updates the context (re-decide and explain what
    changed) or it changes measures (normal what-if, with the user's permission overlay)."""
    profile = memory.load(customer_id) if customer_id else None
    ctx = context if context is not None else (profile.context if profile else UserContext())
    current = advise(home_id, runner, context=ctx, customer_id=None, use_llm=False, remember=False)
    current_measures = canonical(current.scenario).get("selected_measures") or []

    kw = keyword_context(question)
    parsed, source = parse_question(question, current_measures, use_llm=use_llm, client=client)
    if source == "keywords" and kw:
        parsed = WhatIfParse(kind="update_context", add=[], remove=[], unsupported=[], **kw)
    if parsed.kind == "update_context" or _has_context(parsed):
        new_ctx = merge_context(ctx, parsed)
        if customer_id and profile is not None and not profile.records:
            # First visit: record the starting plan so "what changed" has a baseline.
            profile.records.append(memory.record_from(canonical(current.scenario), ctx, current.decision.choice_code))
            memory.save(profile)
        res = advise(home_id, runner, context=new_ctx, customer_id=customer_id, use_llm=use_llm, client=client,
                     question=question)
        if res.changes is None:  # no memory: describe the change against the plan before this question
            prev = memory.record_from(canonical(current.scenario), ctx, current.decision.choice_code)
            cur = memory.record_from(canonical(res.scenario), new_ctx, res.decision.choice_code)
            changes = memory.what_changed(prev, cur)
            if changes:
                contract = canonical(res.scenario)
                contract["decision"] = {**res.decision.facts, **changes}
                res.explanation = explain_sheet(build_factsheet(contract), use_llm=use_llm, question=question,
                                                client=client)
                res.changes = changes
        res.updated_context = True
        return res

    ans = answer_whatif(current.scenario, question, runner, use_llm=use_llm, client=client, context=ctx)
    return AdviceResult(ans.scenario, ans.explanation, current.decision, ctx, None, customer_id, False, ans)


__all__ = ["AdviceResult", "advise", "advise_whatif", "keyword_context", "merge_context", "permissions",
           "keyword_parse"]
