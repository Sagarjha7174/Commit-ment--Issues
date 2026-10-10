"""Compact, address-free payload of one engine ScenarioResult, with a stable key for every number.

Every number an explanation may show comes from here (the engine is the only writer of numbers): `values` maps a
stable dotted key ("package.bill_saving_gbp", "measures.cavity_wall.payback_years", "valuation.high_pct") to the
engine's value. The nested sections are what an LLM, the API or the UI read; no address, full postcode, UPRN,
certificate number or model feature is ever included.
"""
from __future__ import annotations

from typing import Any, Optional

from ..schemas.enums import MEASURE_ORDER

PAYLOAD_VERSION = "llm-payload-v1"
BANNED_KEYS = frozenset({"address", "address1", "address2", "address3", "postcode", "uprn", "certificate_number",
                         "paon", "saon", "street", "postcode_sector"})
CAVEATS = {
    "baseline_benchmark": "The starting energy use is a benchmark for similar homes (NEED), not this home's meter "
                          "readings, unless you gave your own reading.",
    "savings_not_guaranteed": "All savings, carbon, bill and cost figures are estimates, not guarantees.",
    "value_association": "The property-value figure is an association seen in past York sales, not a causal effect "
                         "of retrofitting, and not a valuation.",
    "epc_indicative": "The EPC after retrofit is modelled and indicative; only a new EPC assessment can confirm it.",
}


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _dump(result: Any) -> dict:
    return result.model_dump(mode="json") if hasattr(result, "model_dump") else result


def build_payload(result: Any) -> dict:
    """ScenarioResult (model or JSON dict) -> {sections..., "values": {stable key: number}}."""
    r = _dump(result)
    home = r.get("home") or {}
    sim = r.get("simulation") or {}
    car = r.get("carbon") or {}
    sb, sa = r.get("score_before") or {}, r.get("score_after")
    bills, fin, unc = r.get("bills") or {}, r.get("finance") or {}, r.get("uncertainty")
    val = r.get("valuation") or {}
    base = r.get("baseline") or {}
    sim_ok = sim.get("status") == "ok"

    def score_block(s: Optional[dict]) -> Optional[dict]:
        if not s:
            return None
        return {"status": s.get("status"), "total": s.get("total"), "class": s.get("classification"),
                "range_low": s.get("range_low"), "range_high": s.get("range_high"),
                "completeness": s.get("completeness"), "missing_parts": s.get("missing_parts") or [],
                "key_issues": s.get("key_issues") or [],
                "parts": {p["part"]: {"sub": p.get("sub"), "weight": p.get("weight"), "points": p.get("points"),
                                      "status": p.get("status"), "provenance": p.get("provenance")}
                          for p in s.get("parts") or []}}

    after = sim.get("after") or {}
    package = {
        "measures": list(r.get("measures_applied") or []),
        "blocked": dict(r.get("measures_blocked") or {}),
        "status": sim.get("status"), "reason": sim.get("reason_code"),
        "gas_saving_kwh": sim.get("gas_saving_kwh"), "elec_saving_kwh": sim.get("elec_saving_kwh"),
        "purchased_saving_kwh": sim.get("purchased_saving_kwh"),
        "gas_after_kwh": after.get("gas_total") if sim_ok else None,
        "elec_after_kwh": after.get("elec_import") if sim_ok else None,
        "heat_pump_elec_kwh": after.get("hp_elec") if sim_ok else None,
        "improvement_potential_pct": sim.get("improvement_potential_pct"),
        "improvement_potential_status": sim.get("improvement_potential_status"),
        "carbon_saving_kg": car.get("total_kg"), "carbon_saving_pct": car.get("saving_pct_of_baseline"),
        "carbon_before_kg": car.get("before_kg"), "carbon_after_kg": car.get("after_kg"), "carbon_status": car.get("status"),
        # marginal effect of each measure at its place in the fixed order (these add up to the package totals)
        "steps": {m["measure"]: {"status": m.get("status"), "gas_saving_kwh": m.get("gas_saving_kwh"),
                                 "elec_saving_kwh": m.get("elec_saving_kwh"),
                                 "purchased_saving_kwh": m.get("purchased_saving_kwh")}
                  for m in sim.get("measures") or []},
        "bill_before_gbp": bills.get("before_gbp"), "bill_after_gbp": bills.get("after_gbp"),
        "bill_saving_gbp": bills.get("saving_gbp"), "bill_status": bills.get("status"),
        "gross_cost_gbp": fin.get("gross_cost_gbp"), "grants_gbp": fin.get("grants_gbp"),
        "net_cost_gbp": fin.get("net_cost_gbp"), "payback_years": fin.get("payback_years"),
    }
    loan = (fin.get("illustrative_loan") or {}) if fin else {}
    finance = {"status": fin.get("status") if fin else "not_estimated",
               "grant_notes": fin.get("grant_notes") or [], "cost_provenance": fin.get("cost_provenance"),
               "loan_apr_pct": loan.get("apr_pct"), "loan_term_years": loan.get("term_years"),
               "loan_monthly_repayment_gbp": loan.get("monthly_repayment_gbp"),
               "monthly_bill_saving_gbp": loan.get("monthly_bill_saving_gbp"),
               "saving_covers_repayment": loan.get("saving_covers_repayment"),
               "loan_note": loan.get("status")} if fin else {"status": "not_estimated"}

    measures = {}
    for m, s in (r.get("standalone") or {}).items():
        measures[m] = {k: s.get(k) for k in ("status", "reason", "gas_saving_kwh", "elec_saving_kwh",
                                             "purchased_saving_kwh", "carbon_saving_kg", "bill_saving_gbp",
                                             "gross_cost_gbp", "grants_gbp", "net_cost_gbp", "payback_years")}
    feasibility = {f["measure"]: {"state": f["state"], "suitability": f.get("suitability"),
                                  "reason": f.get("reason_text"), "reason_code": f.get("reason_code"),
                                  "must_verify": f.get("missing_inputs") or []}
                   for f in r.get("feasibility") or []}
    ranking = [{k: x.get(k) for k in ("measure", "rank", "assessor_relevance_prob", "suitability", "feasibility",
                                      "verify", "carbon_per_pound_kg", "bill_saving_gbp")}
               for x in r.get("recommendation_ranking") or []]

    pk = r.get("packages") or {}
    by_id = {p["package_id"]: p for p in pk.get("packages") or []}
    featured = {}
    for f in pk.get("featured") or []:
        p = by_id.get(f.get("package_id")) or {}
        cal = p.get("calibrated") or {}
        featured[f["objective"]] = {
            "label": f.get("label"), "package_id": f.get("package_id"), "message": f.get("message"),
            "measures": p.get("measures") or [], "cost_gbp": p.get("cost_gbp"), "grants_gbp": p.get("grants_gbp"),
            "net_cost_gbp": p.get("net_cost_gbp"), "carbon_saving_kg": p.get("carbon_saving_kg"),
            "carbon_saving_pct": p.get("carbon_saving_pct"), "bill_saving_gbp": p.get("bill_saving_gbp"),
            "payback_years": p.get("payback_years"), "improvement_potential_pct": p.get("improvement_potential_pct"),
            "calibrated_carbon_saving_kg": cal.get("carbon_saving_kg"),
            "calibrated_improvement_potential_pct": cal.get("improvement_potential_pct")}
    combo = r.get("combination_check") or {}
    calibrated = ({"label": combo.get("label"), "gas_saving_kwh": combo.get("gas_saving_kwh"),
                   "elec_saving_kwh": combo.get("elec_saving_kwh"), "carbon_saving_kg": combo.get("carbon_saving_kg"),
                   "improvement_potential_pct": combo.get("improvement_potential_pct")}
                  if combo.get("carbon_saving_kg") is not None else None)

    uncertainty = None
    if unc:
        uncertainty = {"status": unc.get("status"), "label": unc.get("label"), "n_draws": unc.get("n_draws"),
                       "prob_carbon_cut_ge_threshold": unc.get("prob_carbon_cut_ge_threshold"),
                       "prob_bill_falls": unc.get("prob_bill_falls"), "threshold_pct": unc.get("threshold_pct"),
                       **{f"{k}_{q}": (v or {}).get(q) for k, v in (unc.get("percentiles") or {}).items() for q in ("p10", "p50", "p90")}}

    ch = (sa or {}).get("epc_change") or {}
    epc_change = {k: ch.get(k) for k in ("status", "reason", "sap_before", "sap_change", "sap_after_indicative",
                                         "rating_before", "rating_after_indicative", "label", "model_version")}
    valuation = {k: val.get(k) for k in ("status", "reason", "low_pct", "mid_pct", "high_pct", "sap_change",
                                         "current_value_gbp", "current_value_low_gbp", "current_value_high_gbp",
                                         "potential_value_low_gbp", "potential_value_high_gbp", "value_status",
                                         "value_reason", "caveats", "model_versions")}

    payload = {
        "payload_version": PAYLOAD_VERSION,
        "scenario_id": r.get("scenario_id"),
        "home": {"home_id": home.get("home_id"), "display_label": home.get("display_label"),
                 "postcode_outward": home.get("postcode_outward"), "epc_band": home.get("rating"),
                 "sap_score": home.get("sap_score"), "floor_area_m2": home.get("floor_area_m2"),
                 "property_type": home.get("property_type"), "built_form": home.get("built_form"),
                 "age_band": home.get("age_band"), "heating_type": home.get("heating_type"),
                 "stale_epc": home.get("flag_stale_epc")},
        "baseline": {"gas_kwh": base.get("gas_kwh"), "elec_kwh": base.get("elec_kwh"),
                     "gas_provenance": base.get("gas_provenance"), "elec_provenance": base.get("elec_provenance"),
                     "source": base.get("source")},
        "score": {"before": score_block(sb), "after": score_block(sa)},
        "epc_change": epc_change,
        "feasibility": feasibility,
        "recommendation": {"ranking": ranking, "install_order": list(r.get("install_sequence") or [])},
        "package": package,
        "measures": measures,
        "featured": featured,
        "calibrated": calibrated,
        "finance": finance,
        "uncertainty": uncertainty,
        "valuation": valuation,
        "assumptions": {k: v for k, v in (r.get("assumptions") or {}).items() if _num(v) is not None},
        "warnings": list(r.get("warnings") or []),
        "unknowns": list((r.get("audit") or {}).get("unknowns") or []),
        "caveats": dict(CAVEATS),
        "versions": dict(r.get("versions") or {}),
    }
    payload["values"] = flat_values(payload)
    return payload


def flat_values(payload: dict) -> dict[str, float]:
    """Every number in the payload under its stable dotted key (lists of dicts keyed by measure / position)."""
    out: dict[str, float] = {}

    def walk(node: Any, path: list[str]) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("values", "versions"):
                    continue
                walk(v, path + [str(k)])
        elif isinstance(node, list):
            for i, item in enumerate(node):
                tag = item.get("measure") if isinstance(item, dict) and item.get("measure") else str(i)
                walk(item, path + [tag])
        else:
            n = _num(node)
            if n is not None:
                out[".".join(path)] = n

    walk(payload, [])
    return out


def assert_address_free(obj: Any) -> None:
    """Raise if any key in the payload (or any nested dict) is an address field."""
    if isinstance(obj, dict):
        bad = BANNED_KEYS & set(obj)
        if bad:
            raise AssertionError(f"address fields in payload: {sorted(bad)}")
        for v in obj.values():
            assert_address_free(v)
    elif isinstance(obj, list):
        for v in obj:
            assert_address_free(v)


MEASURES = tuple(m.value for m in MEASURE_ORDER)
