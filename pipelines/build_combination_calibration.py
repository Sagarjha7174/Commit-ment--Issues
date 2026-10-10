"""NEED-calibrated factors for multi-measure fabric/controls packages (DECISIONS D17) -> configs/combination_calibration.json.

For each NEED Table 2 combination in docs/validation/simulator_vs_need.json, solve (by bisection) the factor f that,
when every fabric/controls impact in the package is multiplied by f, makes the simulated saving equal the NEED median
(same reference home and basis as pipelines/validate_simulator.py: headline impacts, % of whole-home gas).
Packages with no exact NEED combination use the pooled factor (NEED-sample-weighted mean of the solved factors).

The calibrated estimate is reported next to the engineering estimate, never instead of it (default mode stays
engineering). Four combinations cannot separate in-use effects from selection effects, so the factors are a
reference point, not a validated model.
Usage: .venv/bin/python pipelines/build_combination_calibration.py   (no raw data needed)
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import config  # noqa: E402
from backend.app.schemas.enums import MeasureId as M  # noqa: E402
from backend.app.schemas.property import HomeRecord  # noqa: E402
from backend.app.schemas.scenario import Assumptions  # noqa: E402
from backend.app.services import simulator  # noqa: E402
from backend.app.services.baseline import get_baseline  # noqa: E402
from backend.app.services.simulator import simulate  # noqa: E402

VALIDATION = ROOT / "docs" / "validation" / "simulator_vs_need.json"
OUT = config.CONFIGS / "combination_calibration.json"
VERSION = "combo-cal-v1"
GAS = 12000.0
HEADLINE = Assumptions(segment_impacts=False)


def ref_home(walls: str) -> HomeRecord:
    """Same reference home as pipelines/validate_simulator.py (kept here so this script needs no xlsx reader)."""
    return HomeRecord(home_id="validation", property_type="House", walls_rating="Poor", walls_rating_status="observed",
                      walls_description=walls, roof_rating="Poor", roof_rating_status="observed", age_end=1960.0,
                      roof_description="Pitched, 50 mm loft insulation",   # a loft exists (D20)
                      glazing="double", heating_type="gas_boiler", heating_rating="Good",
                      controls="timer",   # NEED "heat controls" upgrades homes with basic controls -> brief mid 7.5% (D25)
                      solar_pv=False,
                      mains_gas=True, baseline_gas_kwh=GAS, gas_status="population_benchmark",
                      prov_baseline_gas_kwh="population_benchmark", baseline_elec_kwh=3000.0,
                      elec_status="population_benchmark", prov_baseline_elec_kwh="population_benchmark")


def simulated_pct(measures: list[M], factor: float) -> float:
    walls = "Solid brick, as built, no insulation (assumed)" if M.solid_wall in measures else "Cavity wall, as built, no insulation (assumed)"
    h = ref_home(walls)
    orig = simulator.combination_factor
    simulator.combination_factor = lambda ms, c: (factor, None)   # force the trial factor
    try:
        s = simulate(get_baseline(h), h, measures, HEADLINE)
    finally:
        simulator.combination_factor = orig
    assert all(r.status.value == "ok" for r in s.measures)
    return 100 * s.gas_saving_kwh / GAS


def solve(measures: list[M], target_pct: float) -> float:
    lo, hi = 0.0, 1.5
    for _ in range(60):
        mid = (lo + hi) / 2
        if simulated_pct(measures, mid) < target_pct:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def build() -> dict:
    v = json.loads(VALIDATION.read_text())
    rows, wsum, nsum = [], 0.0, 0
    for r in v["rows"]:
        ms = [M(x) for x in r["measures"]]
        f = solve(ms, r["need_median_pct"])
        eng = simulated_pct(ms, 1.0)
        rows.append({"combination": r["combination"], "measures": r["measures"], "need_n": r["need_n"],
                     "need_median_pct": r["need_median_pct"], "engineering_pct": round(eng, 3),
                     "calibrated_pct": round(simulated_pct(ms, f), 3), "factor": round(f, 4)})
        wsum += f * r["need_n"]
        nsum += r["need_n"]
    return {"version": VERSION, "built": date.today().isoformat(), "catalogue": config.catalogue()["version"],
            "source": v["source"], "basis": v["basis"],
            "method": "factor f multiplies every fabric/controls impact in a package of 2+ such measures; f solved so the "
                      "simulated saving on the reference home equals the NEED median; pooled = NEED-n-weighted mean",
            "combinations": rows, "pooled_factor": round(wsum / nsum, 4),
            "caveats": ["4 NEED combinations only; heat controls mapped to smart_thermostat (approximate)",
                        "NEED combination medians below single-measure medians suggest selection and in-use effects, "
                        "so the factor is a reference point, not a physical constant",
                        "reported next to the engineering estimate, never instead of it (default mode engineering)"]}


def main():
    out = build()
    OUT.write_text(json.dumps(out, indent=1))
    print(f"Wrote {OUT.relative_to(ROOT)}")
    for r in out["combinations"]:
        print(f"  {r['combination']:60s} NEED {r['need_median_pct']:6.2f}%  engineering {r['engineering_pct']:6.2f}%  "
              f"factor {r['factor']:.3f} -> {r['calibrated_pct']:6.2f}%")
    print("  pooled factor", out["pooled_factor"])


if __name__ == "__main__":
    main()
