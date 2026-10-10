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
BILL_KEY = "cost_results.bill_saving_gbp"
EPC_KEY = "epc_change.sap_change"
HEAT_PUMP_EPC_NOTE = ("A heat pump cuts carbon, but it can lower the EPC (SAP) rating, because SAP uses electricity "
                      "prices, which are above gas prices; the modelled EPC change and the property-value estimate "
                      "include this effect.")


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
    sc = sheet.get(SCORE_KEY)
    if sc is not None and not sc.available:
        rk = _reason_key(sheet, SCORE_KEY)
        why = f", because {{{rk}}}" if rk else ""
        return [_c("score", "missing_data", f"Your home's Green Home Score is not available{why}, so no class is given.",
                   [SCORE_KEY, CLASS_KEY] + ([rk] if rk else []))]
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
    epc = sheet.get(EPC_KEY)
    if sheet.selected_measures and epc is not None:
        if epc.available:
            out.append(_c("score", "statement",
                          "As an indicative model estimate, not a new EPC assessment, the EPC score {%s|changes} to "
                          "{epc_change.sap_after_indicative}, which would put the home in EPC band "
                          "{epc_change.rating_after_indicative} (band {epc_change.rating_before} today)." % EPC_KEY,
                          [EPC_KEY, "epc_change.sap_after_indicative", "epc_change.rating_after_indicative",
                           "epc_change.rating_before"]))
        else:
            out.append(_missing(sheet, "score", EPC_KEY, "The change in the EPC score"))
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
    if sheet.get("derived.priority_order") is not None and sheet.get("derived.priority_order").available:
        out.append(_c("plan", "statement",
                      "Priority is a separate question from installation order: ranked by how likely an EPC assessor "
                      "is to suggest each one for a home like this, the order is {derived.priority_order}.",
                      ["derived.priority_order"]))
    return out + _package_claims(sheet)


def _package_claims(sheet: FactSheet) -> list[Claim]:
    """The engine's featured packages (one sentence per distinct package), with the NEED-calibrated reference."""
    out, seen = [], set()
    for obj in ("lowest_cost_meeting_threshold", "best_carbon_per_pound", "largest_carbon_saving"):
        base = f"packages.{obj}"
        if sheet.get(f"{base}.measures") is None or sheet.value(f"{base}.measures") in seen:
            continue
        seen.add(sheet.value(f"{base}.measures"))
        keys = [f"{base}.label", f"{base}.measures"]
        text = "Option ({%s.label}): {%s.measures}" % (base, base)
        if sheet.get(f"{base}.net_cost_gbp") is not None and sheet.get(f"{base}.net_cost_gbp").available:
            text += ", costing about {%s.net_cost_gbp} after any grants" % base
            keys.append(f"{base}.net_cost_gbp")
        if sheet.get(f"{base}.carbon_saving_kg") is not None and sheet.get(f"{base}.carbon_saving_kg").available:
            text += ", where carbon emissions would {%s.carbon_saving_kg|change}" % base
            keys.append(f"{base}.carbon_saving_kg")
        out.append(_c("plan", "statement", text + ", as estimated.", keys))
        cal = sheet.get(f"{base}.calibrated_carbon_saving_kg")
        if cal is not None and cal.available:
            out.append(_c("plan", "caveat",
                          "For that combination, measured national data (NEED) points to a smaller figure: emissions "
                          "would {%s.calibrated_carbon_saving_kg|change}." % base, [f"{base}.calibrated_carbon_saving_kg"]))
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
        out = [_c("carbon", "saving", f"Carbon emissions are estimated to fall by {{{CARBON_KEY}}}, calculated "
                                      f"separately for gas and electricity{src}.", keys)]
    elif v < 0:
        out = [_c("carbon", "increase", f"Carbon emissions are estimated to rise by {{{CARBON_KEY}|abs}}, calculated "
                                        f"separately for gas and electricity{src}.", keys)]
    else:
        out = [_c("carbon", "statement", "Carbon emissions are estimated to stay the same.", keys)]
    cal = sheet.get("carbon_results.calibrated_saving_kg")
    if cal is not None and cal.available:
        out.append(_c("carbon", "caveat", "This is the engineering estimate. Measured national data (NEED) for similar "
                                          "combined installations points to a smaller effect: emissions would "
                                          "{carbon_results.calibrated_saving_kg|change}, also an estimate.",
                      ["carbon_results.calibrated_saving_kg"]))
    lo, hi = sheet.get("uncertainty.carbon_saving_kg_p10"), sheet.get("uncertainty.carbon_saving_kg_p90")
    if lo is not None and hi is not None and lo.available and hi.available:
        out.append(_c("carbon", "caveat", "Allowing for uncertainty in the model inputs, in the low case emissions "
                                          "would {uncertainty.carbon_saving_kg_p10|change}, and in the high case they "
                                          "would {uncertainty.carbon_saving_kg_p90|change}; this range is an estimate, not a "
                                          "confidence interval.",
                      ["uncertainty.carbon_saving_kg_p10", "uncertainty.carbon_saving_kg_p90"]))
    return out


def _avail(sheet: FactSheet, key: str) -> bool:
    f = sheet.get(key)
    return f is not None and f.available


def _cost_claims(sheet: FactSheet) -> list[Claim]:
    out = []
    cost = sheet.get(COST_KEY)
    if sheet.selected_measures and cost is not None:
        if cost.available:
            out.append(_c("cost", "statement",
                          f"The selected measures are estimated to cost about {{{COST_KEY}}} in total before grants.",
                          [COST_KEY]))
            g = sheet.get("cost_results.grants_gbp")
            if g is not None and g.available and float(g.value) > 0 and _avail(sheet, "cost_results.net_cost_gbp"):
                out.append(_c("cost", "statement",
                              "Grants of {cost_results.grants_gbp} may apply, subject to eligibility, which would bring "
                              "the cost to about {cost_results.net_cost_gbp}.",
                              ["cost_results.grants_gbp", "cost_results.net_cost_gbp"]))
        else:
            out.append(_missing(sheet, "cost", COST_KEY, "The cost of the selected measures"))
    bill = sheet.get(BILL_KEY)
    if bill is not None and not bill.available:
        out.append(_missing(sheet, "cost", BILL_KEY, "The change in energy bills in pounds"))
    elif bill is not None and sheet.selected_measures:
        keys = [BILL_KEY]
        text = "At today's capped energy prices, the annual energy bill is estimated to {%s|change}" % BILL_KEY
        if _avail(sheet, "cost_results.bill_before_gbp") and _avail(sheet, "cost_results.bill_after_gbp"):
            text += ", from about {cost_results.bill_before_gbp} to about {cost_results.bill_after_gbp} a year"
            keys += ["cost_results.bill_before_gbp", "cost_results.bill_after_gbp"]
        out.append(_c("cost", "statement", text + ".", keys))
        pb = sheet.get("cost_results.payback_years")
        if pb is not None and pb.available:
            out.append(_c("cost", "statement", "Simple payback, the cost after grants divided by the annual bill "
                                               "saving, is about {cost_results.payback_years}.",
                          ["cost_results.payback_years"]))
        elif pb is not None and sheet.get("cost_results.payback_years.reason") is not None:
            out.append(_c("cost", "missing_data", "There is no payback figure, because "
                                                  "{cost_results.payback_years.reason}.",
                          ["cost_results.payback_years", "cost_results.payback_years.reason"]))
        if _avail(sheet, "cost_results.loan_monthly_repayment_gbp") and _avail(sheet, "cost_results.monthly_bill_saving_gbp"):
            out.append(_c("cost", "caveat",
                          "As an illustration only, not a Lloyds product, rate or offer: an illustrative loan for the "
                          "cost after grants at {cost_results.loan_apr_pct} APR over {cost_results.loan_term_years} "
                          "would cost about {cost_results.loan_monthly_repayment_gbp} a month, while the monthly bill "
                          "would {cost_results.monthly_bill_saving_gbp|change}.",
                          ["cost_results.loan_apr_pct", "cost_results.loan_term_years",
                           "cost_results.loan_monthly_repayment_gbp", "cost_results.monthly_bill_saving_gbp"]))
        lo, hi = sheet.get("uncertainty.bill_saving_gbp_p10"), sheet.get("uncertainty.bill_saving_gbp_p90")
        if lo is not None and hi is not None and lo.available and hi.available:
            out.append(_c("cost", "caveat", "Allowing for uncertainty in the inputs, in the low case the annual bill "
                                            "would {uncertainty.bill_saving_gbp_p10|change}, and in the high case it "
                                            "would {uncertainty.bill_saving_gbp_p90|change}.",
                          ["uncertainty.bill_saving_gbp_p10", "uncertainty.bill_saving_gbp_p90"]))
    return out


def _value_claims(sheet: FactSheet) -> list[Claim]:
    facts = [sheet.get(k) for k in VALUE_KEYS]
    if all(f is not None and f.available for f in facts):
        text = ("As an indicative estimate based on past York sales, the selected measures are associated with a "
                f"change in property value of {{{VALUE_KEYS[0]}}} to {{{VALUE_KEYS[1]}}}")
        keys = list(VALUE_KEYS)
        if _avail(sheet, "valuation.uplift_mid_pct"):
            text += ", with a middle estimate of {valuation.uplift_mid_pct}"
            keys.append("valuation.uplift_mid_pct")
        out = [_c("value", "statement", text + ".", keys),
               _c("value", "caveat", "This is an association seen in past sales, not a guarantee and not a proven "
                                     "effect of the retrofit, and it is not a valuation.")]
        if _avail(sheet, "valuation.current_value_gbp"):
            out.append(_c("value", "statement",
                          "For context, the model's indicative estimate of the home's current value is about "
                          "{valuation.current_value_gbp}, with a likely range of {valuation.current_value_low_gbp} to "
                          "{valuation.current_value_high_gbp}.",
                          ["valuation.current_value_gbp", "valuation.current_value_low_gbp",
                           "valuation.current_value_high_gbp"]))
        elif sheet.get("valuation.current_value_gbp.reason") is not None:
            out.append(_c("value", "missing_data", "A pound value for the home is not estimated, because "
                                                   "{valuation.current_value_gbp.reason}.",
                          ["valuation.current_value_gbp", "valuation.current_value_gbp.reason"]))
        return out
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
    if "heat_pump" in sheet.estimated_measures:
        out.append(_c("caveats", "caveat", HEAT_PUMP_EPC_NOTE, [], ["heat_pump"]))
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

