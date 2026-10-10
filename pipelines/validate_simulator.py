"""Compare simulated combination savings with NEED headline COMBINATION figures (Table 2), same basis (% of total gas).

Single-measure headline figures are catalogue inputs, so comparing them would be circular; only combinations are a
check of the interaction model. Writes docs/validation/simulator_vs_need.json.
Usage: .venv/bin/python pipelines/validate_simulator.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import config  # noqa: E402
from backend.app.schemas.enums import MeasureId as M  # noqa: E402
from backend.app.schemas.property import HomeRecord  # noqa: E402
from backend.app.services.baseline import get_baseline  # noqa: E402
from backend.app.services.simulator import simulate  # noqa: E402

SRC = ROOT / "dataset" / "Impact_of_measures_headline_EW_2023.xlsx"
OUT = ROOT / "docs" / "validation" / "simulator_vs_need.json"
TOLERANCE_PP = 5.0
COMBOS = {
    "Cavity Wall Insulation and Loft Insulation": [M.loft_insulation, M.cavity_wall],
    "Solid Wall Insulation and Loft Insulation": [M.loft_insulation, M.solid_wall],
    "Solid Wall Insulation and Heat Controls": [M.solid_wall, M.smart_thermostat],
    "Solid Wall Insulation, Loft Insulation and Heat Controls": [M.loft_insulation, M.solid_wall, M.smart_thermostat],
}
SKIPPED = {"Condensing Boiler and Heat Controls": "condensing boiler is not in the catalogue",
           "Condensing Boiler, Loft Insulation and Heat Controls": "condensing boiler is not in the catalogue"}
GAS = 12000.0  # % savings are scale-free in the simulator; any positive gas gives the same percentages


def need_table2() -> dict:
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    out = {}
    for r in wb["Table 2"].iter_rows(values_only=True):
        vals = [x for x in r if x is not None]
        if len(vals) >= 6 and isinstance(vals[0], str) and "Insulation" in vals[0] or (vals and str(vals[0]).startswith("Condensing")):
            nums = [v for v in vals if isinstance(v, (int, float))]
            if len(nums) >= 5:
                out[vals[0].strip()] = {"n": int(nums[0]), "median_pct": nums[1] * 100, "mean_pct": nums[2] * 100}
    return out


def ref_home(walls: str) -> HomeRecord:
    return HomeRecord(home_id="validation", property_type="House", walls_rating="Poor", walls_rating_status="observed",
                      walls_description=walls, roof_rating="Poor", roof_rating_status="observed", age_end=1960.0,
                      glazing="double", heating_type="gas_boiler", heating_rating="Good", controls="full", solar_pv=False,
                      mains_gas=True, baseline_gas_kwh=GAS, gas_status="population_benchmark",
                      prov_baseline_gas_kwh="population_benchmark", baseline_elec_kwh=3000.0,
                      elec_status="population_benchmark", prov_baseline_elec_kwh="population_benchmark")


def main():
    need = need_table2()
    rows = []
    for name, measures in COMBOS.items():
        n = need[name]
        walls = "Solid brick, as built, no insulation (assumed)" if M.solid_wall in measures else "Cavity wall, as built, no insulation (assumed)"
        h = ref_home(walls)
        sim = simulate(get_baseline(h), h, measures)
        assert all(r.status.value == "ok" for r in sim.measures), name
        pct = 100 * sim.gas_saving_kwh / GAS
        gap = pct - n["median_pct"]
        rows.append({"combination": name, "measures": [m.value for m in measures], "need_n": n["n"],
                     "need_median_pct": round(n["median_pct"], 2), "need_mean_pct": round(n["mean_pct"], 2),
                     "simulated_pct": round(pct, 2), "gap_pp_vs_median": round(gap, 2),
                     "within_tolerance": abs(gap) <= TOLERANCE_PP})
    report = {"source": "DESNZ NEED Impact of measures, headline Table 2 (combinations), installation year 2023, England and Wales",
              "basis": "% of whole-home annual gas (same basis as the catalogue single-measure inputs)",
              "tolerance_pp": TOLERANCE_PP, "catalogue": config.catalogue()["version"], "rows": rows,
              "skipped": SKIPPED,
              "notes": ["Heat Controls in NEED is mapped to smart_thermostat (brief range, not validated): approximate.",
                        "Single-measure NEED figures are catalogue inputs; comparing them would be circular, so only combinations are checked."]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1))
    print(f"Wrote {OUT.relative_to(ROOT)}")
    for r in rows:
        print(f"  {r['combination'][:58]:58s} NEED median {r['need_median_pct']:6.2f}%  sim {r['simulated_pct']:6.2f}%  "
              f"gap {r['gap_pp_vs_median']:+6.2f} pp  {'OK' if r['within_tolerance'] else 'OUTSIDE'} (±{TOLERANCE_PP})")


if __name__ == "__main__":
    main()
