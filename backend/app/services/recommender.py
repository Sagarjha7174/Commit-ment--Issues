"""Relevance ranking of a home's feasible measures (M5). ML only reorders; it never adds an infeasible measure.

Priority: calibrated probability that the EPC assessor would recommend the measure (shipped classifiers; measures
without one use their train prevalence, D37), ties broken by carbon saved per pound (net). If the ranking model did
not beat the engine order on validation, the engine order is used (suitability High > Medium > Low, catalogue order).
Install sequence is separate: the engine's fixed physical order (fabric -> glazing -> controls -> heat pump -> PV).
Agreement with assessors means "consistent with the EPC assessor", not "feasible" or "worth doing".
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from ..ml import features as F
from ..ml import registry
from ..schemas.enums import MEASURE_ORDER, FeasibilityState, MeasureId
from ..schemas.property import HomeRecord
from ..schemas.retrofit import FeasibilityItem

SUIT_RANK = {"High": 3, "Medium": 2, "Low": 1}
LABEL = "probability that an EPC assessor would recommend this measure for a home like this (calibrated); not feasibility"


def _prevalence(tables: dict, m: str, home: HomeRecord) -> Optional[float]:
    t = tables.get(m)
    if not t:
        return None
    return t["cell"].get(f"{home.property_type}|{home.age_band}", t["type"].get(str(home.property_type), t["all"]))


def probability(home: HomeRecord, m: MeasureId) -> tuple[Optional[float], str]:
    """(probability, basis) for one measure; (None, reason) when no model or table is available."""
    model = registry.get(f"rec_{m.value}")
    if model is not None:
        raw = float(model.predict([F.features(F.state_from_home(home), "recommender")])[0])
        iso = model.meta["isotonic"]
        return float(np.interp(raw, iso["x"], iso["y"])), f"classifier {model.version} (isotonic calibrated)"
    rk = registry.get_json("recommender_ranking")
    if rk is not None:
        p = _prevalence(rk["b1_prevalence"], m.value, home)
        if p is not None:
            return float(p), "train prevalence for this property type and age band (no classifier, D37)"
    return None, "no relevance model"


def ranking(home: HomeRecord, feas: list[FeasibilityItem], standalone: dict) -> Optional[list[dict]]:
    """Ranked non-infeasible measures, or None when nothing is feasible."""
    use_model = registry.get_json("recommender_ranking") is not None   # shipped only if it beat the engine order
    rows = []
    for f in feas:
        if f.state == FeasibilityState.infeasible:
            continue
        sa = standalone.get(f.measure.value, {})
        net, carbon = sa.get("net_cost_gbp"), sa.get("carbon_saving_kg")
        cpp = carbon / net if (carbon is not None and net) else None
        p, basis = probability(home, f.measure) if use_model else (None, "engine order (ranking model not shipped)")
        rows.append({"measure": f.measure.value, "assessor_relevance_prob": None if p is None else round(p, 4),
                     "basis": basis, "suitability": f.suitability.value if f.suitability else None,
                     "feasibility": f.state.value, "verify": f.state == FeasibilityState.needs_verification,
                     "must_verify": list(f.missing_inputs), "carbon_per_pound_kg": None if cpp is None else round(cpp, 4),
                     "bill_saving_gbp": sa.get("bill_saving_gbp")})
    if not rows:
        return None

    def key(r):
        order = MEASURE_ORDER.index(MeasureId(r["measure"]))
        if use_model:
            return (-(r["assessor_relevance_prob"] if r["assessor_relevance_prob"] is not None else -1),
                    -(r["carbon_per_pound_kg"] if r["carbon_per_pound_kg"] is not None else -1e9), order)
        return (-SUIT_RANK.get(r["suitability"], 0), order)

    rows.sort(key=key)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
        r["label"] = LABEL if use_model else "engine order: suitability, then catalogue order"
    return rows


def install_sequence(ranked: Optional[list[dict]]) -> Optional[list[str]]:
    """'Do in this order': the engine's fixed physical order (interactions: fabric before heat pump, PV last)."""
    if not ranked:
        return None
    chosen = {r["measure"] for r in ranked}
    return [m.value for m in MEASURE_ORDER if m.value in chosen]
