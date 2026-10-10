"""Monte Carlo ranges for one home's retrofit package (DECISIONS D28).

What varies (independently, per draw) is the uncertainty in the *model inputs for this home*:
- NEED-based impacts (loft, cavity, solid wall, PV): headline triangular(low, mid, high) + the home's segment
  adjustment + normal(0, empirical-Bayes posterior sd of the segments used);
- brief ranges: double glazing uniform(8%, 12%); thermostat uniform over the levels adjacent to its controls placement;
- heat-pump SCOP triangular(2.44, 2.80, 3.5) (D24); existing boiler efficiency +/- 0.05 (D18);
- space/water split of heating energy uniform(0.65, 0.85);
- baseline per fuel: lognormal household spread around the NEED cell median (when calibrated, D21/C1); not varied for
  user-provided readings or an observed zero (no mains gas).
The NEED household outcome spread (p5..p95 per measure, which includes changes unrelated to the retrofit such as
occupancy) is reported per measure as context and NOT compounded across measures.
Seeded from the scenario id, so the same request gives the same ranges. This is not a confidence interval.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .. import config
from ..schemas.enums import MeasureId, ValueStatus
from ..schemas.property import HomeRecord
from ..schemas.retrofit import FeasibilityItem
from ..schemas.scenario import Assumptions, Baseline
from . import impacts, units
from .carbon import carbon_change
from .money import bill_change
from .simulator import simulate

LABEL = ("model-input uncertainty for this home (Monte Carlo): ranges show how much the estimate moves with the "
         "documented input ranges; not a confidence interval and not a guarantee")
N_DRAWS = 300
NEED_MEASURES = ("loft_insulation", "cavity_wall", "solid_wall", "solar_pv")
LEVELS = ("low", "mid", "high")


def _tri(rng, lo, mode, hi):
    lo, hi = min(lo, mode), max(hi, mode)
    return float(mode) if hi - lo < 1e-12 else float(rng.triangular(lo, mode, hi))


def _segment_posterior_sd(measure_id: str, home: HomeRecord) -> float:
    _, detail = impacts.adjustment(measure_id, home)
    table = impacts.shrinkage(measure_id)
    var = 0.0
    for dim, d in detail.items():
        if not isinstance(d, dict) or not d.get("used"):
            continue
        row = table.get(dim, {}).get(d.get("segment"))
        if row is not None:
            var += row["weight"] * row["se"] ** 2   # posterior variance tau2*se2/(tau2+se2)
    return math.sqrt(var)


def draw_impact(rng, m: MeasureId, home: HomeRecord, a: Assumptions) -> float:
    spec = config.measure_spec(m.value)["impact"]
    if m.value in NEED_MEASURES:
        head = _tri(rng, spec["low"], spec["mid"], spec["high"])
        adj = 0.0
        if a.segment_impacts:
            adj, _ = impacts.adjustment(m.value, home)
            adj += rng.normal(0.0, _segment_posterior_sd(m.value, home))
        return max(head + adj, 0.0)
    if m == MeasureId.smart_thermostat:
        lvl = LEVELS.index(impacts.thermostat_level(home, a.impact_level.value))
        lo, hi = LEVELS[max(lvl - 1, 0)], LEVELS[min(lvl + 1, 2)]
        return float(rng.uniform(spec[lo], spec[hi]))
    return float(rng.uniform(spec["low"], spec["high"]))


def run(home: HomeRecord, baseline: Baseline, feas: list[FeasibilityItem], measures: list[MeasureId],
        a: Assumptions, seed_text: str, n: int = N_DRAWS, threshold_pct: float = 10.0) -> dict:
    base_sim = simulate(baseline, home, measures, a, feas)
    if base_sim.status != ValueStatus.ok or not measures:
        return {"status": ValueStatus.unavailable.value, "reason": base_sim.reason_code or "no measures"}
    rng = np.random.default_rng(int(seed_text[:16], 16) if seed_text else 0)
    scop = config.catalogue_globals()["heat_pump_scop"]
    eff0 = units.resolve(a, home).boiler_efficiency
    spread = ((config.engine_calibration() or {}).get("baseline_spread") or {})
    varied = ["NEED impacts (headline range + segment posterior)", "brief ranges (glazing, thermostat)",
              "heat-pump SCOP 2.44-2.80-3.5", "boiler efficiency +/-0.05", "space/water split 0.65-0.85"]
    # every baseline except the customer's own reading is an estimate for a typical home of this kind
    vary_gas = baseline.gas_provenance.value != "user_provided" and baseline.gas_status != "no_mains_gas" and spread.get("gas_sigma_log")
    vary_elec = baseline.elec_provenance.value != "user_provided" and spread.get("elec_sigma_log")
    if vary_gas or vary_elec:
        varied.append("baseline household spread around the NEED benchmark")
    not_varied = ["occupancy and behaviour", "weather", "installation quality", "prices",
                  *([] if (vary_gas or vary_elec) else ["baseline spread (run make engine-cal)"])]

    rows = []
    for _ in range(n):
        da = a.model_copy(update={
            "heat_pump_scop": _tri(rng, scop["low"], scop["mid"], scop["high"]),
            "boiler_efficiency": float(min(max(eff0 + rng.uniform(-0.05, 0.05), 0.55), 0.95)),
            "space_share_of_heat_water_gas": float(rng.uniform(0.65, 0.85)),
        })
        b = baseline
        upd = {}
        if vary_gas and baseline.gas_kwh:
            upd["gas_kwh"] = baseline.gas_kwh * math.exp(rng.normal(0, spread["gas_sigma_log"]))
        if vary_elec and baseline.elec_kwh:
            upd["elec_kwh"] = baseline.elec_kwh * math.exp(rng.normal(0, spread["elec_sigma_log"]))
        if upd:
            b = baseline.model_copy(update=upd)
        overrides = {m: draw_impact(rng, m, home, a) for m in measures if m != MeasureId.heat_pump}
        s = simulate(b, home, measures, da, feas, impact_overrides=overrides)
        if s.status != ValueStatus.ok:
            continue
        c = carbon_change(s)
        bill = bill_change(s, a)
        rows.append((s.gas_saving_kwh, s.elec_saving_kwh, s.purchased_saving_kwh, c.total_kg,
                     c.saving_pct_of_baseline or 0.0, bill.get("saving_gbp", float("nan")),
                     s.improvement_potential_pct if s.improvement_potential_pct is not None else float("nan")))
    if not rows:
        return {"status": ValueStatus.unavailable.value, "reason": "no draw could be simulated"}
    arr = np.array(rows, dtype=float)
    names = ("gas_saving_kwh", "elec_saving_kwh", "purchased_saving_kwh", "carbon_saving_kg", "carbon_saving_pct",
             "bill_saving_gbp", "improvement_potential_pct")
    pct = {}
    for i, k in enumerate(names):
        col = arr[:, i][np.isfinite(arr[:, i])]
        pct[k] = None if not len(col) else {q: round(float(np.percentile(col, int(q[1:]))), 2) for q in ("p10", "p50", "p90")}
    context = {}
    for m in measures:
        disp = config.measure_spec(m.value).get("household_dispersion")
        if disp:
            context[m.value] = {k: disp[k] for k in ("p5", "q1", "q3", "p95")} | {
                "note": "spread of measured outcomes in NEED homes (includes changes unrelated to the retrofit)"}
    return {"status": ValueStatus.ok.value, "label": LABEL, "n_draws": len(rows), "seed": seed_text[:16],
            "percentiles": pct, "threshold_pct": threshold_pct,
            "prob_carbon_cut_ge_threshold": round(float((arr[:, 4] >= threshold_pct).mean()), 3),
            "prob_bill_falls": round(float((arr[:, 5] > 0).mean()), 3),
            "inputs_varied": varied, "not_varied": not_varied, "household_spread_context": context}
