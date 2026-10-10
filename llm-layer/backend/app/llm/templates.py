"""Deterministic explanations with no LLM.

Used three ways: the fallback when the LLM fails the checker twice or the API
is down, the app's template mode, and the baseline the LLM is evaluated
against. Every draft built here must pass checker.check() for any valid
scenario; tests/llm/test_llm_templates.py enforces it on every fixture.
"""

from __future__ import annotations

from .checker import CARBON_KEY, CLASS_KEY, ELEC_KEY, GAS_KEY, MEASURED_PROVENANCE, SCORE_KEY, VALUE_KEYS
from .claims import Claim, ExplanationDraft
from .facts_view import FactSheet
from .measures import display_name

PURCHASED_KEY = "energy_results.change.purchased_saving_kwh"
POTENTIAL_KEY = "energy_results.change.improvement_potential_pct"
HP_ELEC_KEY = "energy_results.after.heat_pump_elec_kwh"
COST_KEY = "cost_results.package_cost_gbp"
BILL_KEY = "cost_results.bill_change_gbp"


def _c(section: str, type_: str, text: str, keys: list[str] | None = None, measures: list[str] | None = None) -> Claim:
    return Claim(section=section, type=type_, text=text, keys=keys or [], measures=measures or [])


def _reason_key(sheet: FactSheet, key: str) -> str | None:
    rk = f"{key}.reason"
    return rk if sheet.get(rk) is not None else None


def _missing(sheet: FactSheet, section: str, key: str, what: str) -> Claim:
    rk = _reason_key(sheet, key)
    if rk:
        return _c(section, "missing_data", f"{what} is not estimated, because {{{rk}}}.", [key, rk])
    return _c(section, "missing_data", f"{what} is not estimated for this home.", [key])


def _fuel_change(sheet: FactSheet, key: str, fuel: str, *, why_rise: str = "") -> Claim | None:
    f = sheet.get(key)
    if f is None:
        return None
    if not f.available:
        return _missing(sheet, "energy", key, f"The change in {fuel}")
    v = float(f.value)
    if v > 0:
        return _c("energy", "saving", f"{fuel.capitalize()} is estimated to fall by {{{key}}}.", [key])
    if v < 0:
        return _c("energy", "increase", f"{fuel.capitalize()} is estimated to rise by {{{key}|abs}}{why_rise}.", [key])
    return _c("energy", "statement", f"Based on the estimates, {fuel} is not expected to change.", [key])


def _score_claims(sheet: FactSheet) -> list[Claim]:
    out = [_c("score", "statement",
              f"Your home's Green Home Score is {{{SCORE_KEY}}}, which is classed as {{{CLASS_KEY}}}.",
              [SCORE_KEY, CLASS_KEY])]
    rng = sheet.get("green_home_score.before.range")
    if rng is not None and rng.available and rng.value[0] != rng.value[1]:
        keys = ["green_home_score.before.range", "green_home_score.before.completeness"]
        out.append(_c("score", "missing_data",
                      "Some information is missing, so the true score could be anywhere in the range "
                      "{green_home_score.before.range}; {green_home_score.before.completeness} parts of the "
                      "score use known data.", [k for k in keys if sheet.get(k) is not None]))
    drags = sheet.get("derived.score_drags")
    if drags is not None and drags.available:
        out.append(_c("score", "statement", "The parts losing the most points are {derived.score_drags}.",
                      ["derived.score_drags"]))
    after = sheet.get("green_home_score.after.total")
    if sheet.selected_measures and after is not None and after.available:
        out.append(_c("score", "statement",
                      "With the selected measures, the score is estimated to become "
                      "{green_home_score.after.total} ({green_home_score.after.class}).",
                      ["green_home_score.after.total", "green_home_score.after.class"]))
    return out


def _plan_claims(sheet: FactSheet) -> list[Claim]:
    sel = sheet.selected_measures
    if not sel:
        return [_c("plan", "statement", "No measures are selected in this scenario.")]
    text = "The suggested measures, in the order they are applied, are: {derived.plan_order}."
    if any(sheet.feasibility.get(m) and sheet.feasibility[m].state == "needs_verification" for m in sel):
        text += " Some of these need checking on site before they can be confirmed."
    out = [_c("plan", "recommendation", text, ["derived.plan_order"], sel)]
    if sheet.get("derived.order_reason") is not None:
        out.append(_c("plan", "statement", "Why this order: {derived.order_reason}.", ["derived.order_reason"]))
    return out


def _energy_claims(sheet: FactSheet) -> list[Claim]:
    sel = sheet.selected_measures
    why = ", because the heat pump runs on electricity instead of gas" if "heat_pump" in sel else ""
    out = [c for c in (_fuel_change(sheet, GAS_KEY, "gas use"),
                       _fuel_change(sheet, ELEC_KEY, "electricity bought from the grid", why_rise=why)) if c]

    hp = sheet.get(HP_ELEC_KEY)
    if "heat_pump" in sel and hp is not None and hp.available and float(hp.value) > 0:
        out.append(_c("energy", "statement", f"The heat pump itself is estimated to use {{{HP_ELEC_KEY}}}.",
                      [HP_ELEC_KEY], ["heat_pump"]))

    total = sheet.get(PURCHASED_KEY)
    pot = sheet.get(POTENTIAL_KEY)
    if total is not None and total.available and float(total.value) > 0:
        text = "In total, the energy the home buys is estimated to fall by {%s}" % PURCHASED_KEY
        keys = [PURCHASED_KEY]
        if pot is not None and pot.available:
            text += ", a cut of {%s}" % POTENTIAL_KEY
            keys.append(POTENTIAL_KEY)
        out.append(_c("energy", "saving", text + ".", keys))
    elif total is not None and total.available and float(total.value) < 0:
        out.append(_c("energy", "increase",
                      "In total, the energy the home buys is estimated to rise by {%s|abs}." % PURCHASED_KEY,
                      [PURCHASED_KEY]))

    rows = 0
    while sheet.get(f"energy_results.per_measure.{rows}.measure") is not None:
        rows += 1
    for i in range(rows):
        name_key = f"energy_results.per_measure.{i}.measure"
        measure = _per_measure_id(sheet, i)
        for fuel_key, fuel in ((f"energy_results.per_measure.{i}.gas_saving_kwh", "gas use"),
                               (f"energy_results.per_measure.{i}.elec_saving_kwh", "grid electricity")):
            f = sheet.get(fuel_key)
            if f is None or not f.available or float(f.value) == 0:
                continue
            if float(f.value) > 0:
                out.append(_c("energy", "saving", f"With {{{name_key}}}, {fuel} is estimated to fall by "
                                                  f"{{{fuel_key}}}.", [name_key, fuel_key], [measure]))
            else:
                out.append(_c("energy", "increase", f"With {{{name_key}}}, {fuel} is estimated to rise by "
                                                    f"{{{fuel_key}|abs}}.", [name_key, fuel_key], [measure]))
    if len(sel) > 1:
        out.append(_c("energy", "caveat",
                      "Each measure's estimated saving is worked out on the energy left after the measures "
                      "before it, so these figures already allow for how the measures interact."))
    if "solar_pv" in sel:
        out.append(_c("energy", "caveat",
                      "Solar panels cut the electricity bought from the grid; they do not change how much "
                      "energy the home itself needs.", [], ["solar_pv"]))
    return out


def _per_measure_id(sheet: FactSheet, i: int) -> str:
    raw = sheet.value(f"energy_results.per_measure.{i}.measure")
    for m in sheet.selected_measures:
        if display_name(m) == raw:
            return m
    return sheet.selected_measures[i] if i < len(sheet.selected_measures) else ""


def _carbon_claims(sheet: FactSheet) -> list[Claim]:
    f = sheet.get(CARBON_KEY)
    if f is None:
        return []
    if not f.available:
        return [_missing(sheet, "carbon", CARBON_KEY, "The change in carbon emissions")]
    keys = [CARBON_KEY]
    src = ""
    if sheet.get("carbon_results.factors_version") is not None:
        src = " using {carbon_results.factors_version} emissions factors"
        keys.append("carbon_results.factors_version")
    v = float(f.value)
    if v > 0:
        return [_c("carbon", "saving", f"Carbon emissions are estimated to fall by {{{CARBON_KEY}}}, calculated "
                                       f"separately for gas and electricity{src}.", keys)]
    if v < 0:
        return [_c("carbon", "increase", f"Carbon emissions are estimated to rise by {{{CARBON_KEY}|abs}}, calculated "
                                         f"separately for gas and electricity{src}.", keys)]
    return [_c("carbon", "statement", "Carbon emissions are estimated to stay the same.", keys)]


def _cost_claims(sheet: FactSheet) -> list[Claim]:
    out = []
    cost = sheet.get(COST_KEY)
    if sheet.selected_measures and cost is not None:
        if cost.available:
            out.append(_c("cost", "statement",
                          f"The selected measures are estimated to cost about {{{COST_KEY}}} in total.", [COST_KEY]))
        else:
            out.append(_missing(sheet, "cost", COST_KEY, "The cost of the selected measures"))
    bill = sheet.get(BILL_KEY)
    if bill is not None and not bill.available:
        out.append(_missing(sheet, "cost", BILL_KEY, "The change in energy bills in pounds"))
    return out


def _value_claims(sheet: FactSheet) -> list[Claim]:
    facts = [sheet.get(k) for k in VALUE_KEYS]
    if all(f is not None and f.available for f in facts):
        return [
            _c("value", "statement",
               "As an indicative estimate based on past sales, the full package is associated with a change in "
               f"property value of {{{VALUE_KEYS[0]}}} to {{{VALUE_KEYS[1]}}}.", list(VALUE_KEYS)),
            _c("value", "caveat", "This is an association seen in past sales, not a guarantee and not a proven "
                                  "effect of the retrofit."),
        ]
    for k in VALUE_KEYS:
        if sheet.get(f"{k}.reason") is not None:
            return [_missing(sheet, "value", k, "A change in property value")]
    if sheet.get("valuation.reason") is not None:
        return [_c("value", "missing_data", "A change in property value is not estimated, because "
                                            "{valuation.reason}.", ["valuation.reason"])]
    return [_c("value", "missing_data", "A change in property value is not estimated for this scenario.")]


def _not_suitable_claims(sheet: FactSheet) -> list[Claim]:
    out = []
    for state, lead in (("infeasible", "Not suitable"), ("needs_verification", "Needs checking first")):
        for m in sheet.measures_in(state):
            name_key, reason_key = f"feasibility.{m}.measure", f"feasibility.{m}.reason"
            if sheet.get(reason_key) is not None:
                out.append(_c("not_suitable", "feasibility", f"{lead}: {{{name_key}}}, because {{{reason_key}}}.",
                              [name_key, reason_key], [m]))
            else:
                out.append(_c("not_suitable", "feasibility", f"{lead}: {{{name_key}}}.", [name_key], [m]))
    return out


def _caveat_claims(sheet: FactSheet) -> list[Claim]:
    out = [_c("caveats", "caveat", f"Note: {{{k}}}", [k]) for k in sheet.warning_keys]
    if sheet.get("derived.missing_inputs") is not None:
        out.append(_c("caveats", "missing_data", "Details about the home that are missing: {derived.missing_inputs}.",
                      ["derived.missing_inputs"]))
    if sheet.baseline_provenance and not (sheet.baseline_provenance & MEASURED_PROVENANCE):
        out.append(_c("caveats", "caveat", "The starting energy use is not a meter reading from this home."))
    out.append(_c("caveats", "caveat", "All savings, carbon and cost figures are estimates, not guarantees."))
    if sheet.get("assumptions") is not None and sheet.get("assumptions").available:
        out.append(_c("caveats", "caveat", "Main assumptions: {assumptions}.", ["assumptions"]))
    return out


def _context_claims(sheet: FactSheet) -> list[Claim]:
    """Decision-context sentences: code-written facts, cited by placeholder."""
    out = []
    for key, section, type_, lead in (
            ("decision.situation", "fit", "statement", "Your situation: "),
            ("decision.plan_choice", "fit", "statement", "Why this plan: "),
            ("decision.who_benefits", "fit", "statement", "Who pays and who benefits: "),
            ("decision.budget_fit", "fit", "statement", "Budget: "),
            ("decision.excluded", "fit", "statement", "Left out at your request: "),
            ("decision.changes_summary", "fit", "statement", "Since last time: "),
            ("decision.next_steps", "next_steps", "caveat", "Before you start: "),
            ("decision.completed_note", "caveats", "caveat", "Note: "),
            ("decision.not_assessed", "caveats", "caveat", "Not assessed here: ")):
        f = sheet.get(key)
        if f is not None and f.available:
            out.append(_c(section, type_, f"{lead}{{{key}}}.", [key]))
    for key, what in (("decision.changes.carbon_saving_kg", "estimated emissions would"),
                      ("decision.changes.extra_cost_gbp", "the estimated cost would")):
        f = sheet.get(key)
        if f is not None and f.available:  # the |change filter writes the direction from the value's sign
            out.append(_c("fit", "statement", f"Compared with your last plan, {what} {{{key}|change}}.", [key]))
    return out


def template_report(sheet: FactSheet) -> ExplanationDraft:
    claims: list[Claim] = []
    claims += _context_claims(sheet)
    claims += _score_claims(sheet)
    if sheet.get("derived.issues") is not None and sheet.get("derived.issues").available:
        claims.append(_c("issues", "statement", "Key issues: {derived.issues}.", ["derived.issues"]))
    claims += _plan_claims(sheet)
    if sheet.selected_measures:
        claims += _energy_claims(sheet)
        claims += _carbon_claims(sheet)
    claims += _cost_claims(sheet)
    claims += _value_claims(sheet)
    claims += _not_suitable_claims(sheet)
    claims += _caveat_claims(sheet)
    return ExplanationDraft(claims=claims)

