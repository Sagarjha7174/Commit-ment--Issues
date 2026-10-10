"""Bills, grants, payback and an illustrative loan (DECISIONS D26, D27).

Bills: unit rates and standing charges from configs/energy_prices.json (Ofgem cap), or scenario overrides
(Assumptions.gas_price_p / elec_price_p). The gas standing charge is saved only when no gas is left after the retrofit
(cooking gas keeps the connection). Solar export is not credited, so PV bill savings are conservative.
Grants: configs/grants.json evaluated at its fixed as_of date; subject to scheme eligibility.
Finance: simple payback and a level monthly repayment at an illustrative APR (configs/finance.json, not an offer).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from .. import config
from ..schemas.enums import MeasureId, ValueStatus
from ..schemas.property import HomeRecord
from ..schemas.retrofit import EndUses, SimResult
from ..schemas.scenario import Assumptions
from .costs import package_cost

TOL = 1e-6


def prices(a: Optional[Assumptions] = None) -> dict:
    p = config.energy_prices()
    gas_p = a.gas_price_p if a is not None and a.gas_price_p is not None else p["gas"]["unit_p_per_kwh"]
    elec_p = a.elec_price_p if a is not None and a.elec_price_p is not None else p["elec"]["unit_p_per_kwh"]
    src = p["version"] if (a is None or (a.gas_price_p is None and a.elec_price_p is None)) else f"{p['version']} with scenario override"
    return {"gas_p_per_kwh": gas_p, "elec_p_per_kwh": elec_p, "gas_standing_p_per_day": p["gas"]["standing_p_per_day"],
            "elec_standing_p_per_day": p["elec"]["standing_p_per_day"], "source": src}


def annual_bill(eu: EndUses, pr: dict, gas_connected: bool) -> dict:
    gas = eu.gas_total * pr["gas_p_per_kwh"] / 100
    elec = eu.elec_import * pr["elec_p_per_kwh"] / 100
    standing = 365 * (pr["elec_standing_p_per_day"] + (pr["gas_standing_p_per_day"] if gas_connected else 0.0)) / 100
    return {"gas_gbp": gas, "elec_gbp": elec, "standing_gbp": standing, "total_gbp": gas + elec + standing}


def bill_change(sim: SimResult, a: Optional[Assumptions] = None) -> dict:
    if sim.status != ValueStatus.ok:
        return {"status": ValueStatus.unavailable.value, "reason": sim.reason_code or "simulation unavailable"}
    pr = prices(a)
    connected_before = sim.before.gas_total > TOL
    connected_after = sim.after.gas_total > TOL
    before = annual_bill(sim.before, pr, connected_before)
    after = annual_bill(sim.after, pr, connected_after)
    notes = ["estimate at capped unit rates; not a quote", "solar export not credited"]
    if connected_before and not connected_after:
        notes.append("no gas left: gas standing charge saved (assumes the gas meter is removed)")
    elif connected_after and sim.after.gas_space + sim.after.gas_water <= TOL and connected_before:
        notes.append("gas kept for cooking: gas standing charge still paid")
    return {"status": ValueStatus.ok.value, "before_gbp": round(before["total_gbp"], 2), "after_gbp": round(after["total_gbp"], 2),
            "saving_gbp": round(before["total_gbp"] - after["total_gbp"], 2),
            "gas_saving_gbp": round(before["gas_gbp"] - after["gas_gbp"], 2),
            "elec_saving_gbp": round(before["elec_gbp"] - after["elec_gbp"], 2),
            "standing_saving_gbp": round(before["standing_gbp"] - after["standing_gbp"], 2),
            "prices": pr, "notes": notes, "sign": "positive = bill falls"}


def grants_for(measures: list[MeasureId], home: HomeRecord, gross_by_measure: dict[str, float]) -> tuple[float, list[str]]:
    g = config.grants()
    as_of = date.fromisoformat(g["as_of"])
    total, notes = 0.0, []
    for gr in g["grants"]:
        m = MeasureId(gr["measure"])
        if m not in measures:
            continue
        el = gr["eligibility"]
        if g.get("region_nation") not in el["nations"] or home.heating_type not in el["replaces_heating_types"]:
            notes.append(f"{gr['name']}: not eligible (nation or current heating)")
            continue
        amount, why = gr["amount_gbp"], "standard rate"
        up = gr.get("uplift")
        if up and up["condition"] == "off_gas" and home.mains_gas is False and \
                date.fromisoformat(up["valid_from"]) <= as_of <= date.fromisoformat(up["valid_to"]):
            amount, why = up["amount_gbp"], up["note"]
        amount = min(amount, gross_by_measure.get(m.value, amount))
        total += amount
        notes.append(f"{gr['name']}: £{amount:,.0f} ({why}; {gr['eligibility_note']})")
    return total, notes


def loan_monthly(principal: float) -> tuple[float, dict]:
    f = config.finance()
    r, n = f["apr_pct"] / 100 / 12, int(f["term_years"] * 12)
    pay = principal / n if r == 0 else principal * r / (1 - (1 + r) ** -n)
    return pay, {"apr_pct": f["apr_pct"], "term_years": f["term_years"], "status": f["status"]}


def finance_summary(measures: list[MeasureId], home: HomeRecord, bill: dict) -> dict:
    """Gross and net cost, grants, payback and an illustrative loan for one package."""
    from .costs import measure_cost
    gross_by = {m.value: measure_cost(m, home)[0] for m in measures}
    gross, prov = package_cost(measures, home)
    if gross is None:
        return {"status": ValueStatus.unavailable.value, "reason": prov}
    grants, gnotes = grants_for(measures, home, {k: v for k, v in gross_by.items() if v is not None})
    net = max(gross - grants, 0.0)
    saving = bill.get("saving_gbp") if bill.get("status") == ValueStatus.ok.value else None
    out = {"status": ValueStatus.ok.value, "gross_cost_gbp": round(gross, 2), "grants_gbp": round(grants, 2),
           "net_cost_gbp": round(net, 2), "cost_provenance": prov, "grant_notes": gnotes,
           "annual_bill_saving_gbp": saving}
    if saving is not None and saving > 0:
        out["payback_years"] = round(net / saving, 1)
    else:
        out["payback_years"] = None
        out["payback_note"] = "the bill does not fall, so the cost is not paid back from bills (carbon is the benefit)"
    if net > 0:
        pay, terms = loan_monthly(net)
        out["illustrative_loan"] = {**terms, "monthly_repayment_gbp": round(pay, 2),
                                    "monthly_bill_saving_gbp": round(saving / 12, 2) if saving is not None else None,
                                    "saving_covers_repayment": (saving / 12 >= pay) if saving is not None else None}
    return out
