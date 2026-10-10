"""M7: eval/test_predictions.csv, one row per TEST home and scenario ("baseline" and "all_feasible"), schema of
docs/DATA.md §5. Every number comes from the engine (scenario_builder.build); no addresses or full postcodes.

Usage: .venv/bin/python pipelines/ml/write_test_predictions.py
"""
from __future__ import annotations

import time

import pandas as pd

from common import ROOT  # noqa: E402
from backend.app.data.loaders import homes_frame  # noqa: E402
from backend.app.ml import registry  # noqa: E402
from backend.app.ml.privacy import assert_no_restricted  # noqa: E402
from backend.app.schemas.enums import ValueStatus  # noqa: E402
from backend.app.schemas.property import home_from_row  # noqa: E402
from backend.app.schemas.scenario import ScenarioRequest  # noqa: E402
from backend.app.services import energy_model  # noqa: E402
from backend.app.services.scenario_builder import build  # noqa: E402
from backend.app.services.score import PARTS  # noqa: E402

OUT = ROOT / "eval" / "test_predictions.csv"


def row(r, scenario: str, home) -> dict:
    s = r.score_before if scenario == "baseline" else r.score_after
    sim, b = r.simulation, r.baseline
    applied = scenario != "baseline" and sim.status == ValueStatus.ok
    out = {"property_id": home.home_id, "split": "test", "scenario": scenario,
           "scenario_id": "baseline" if scenario == "baseline" else ("+".join(m.value for m in r.measures_applied) or "none"),
           "engine_scenario_hash": r.scenario_id,
           "model_version": ";".join(f"{k}={v}" for k, v in sorted(r.versions.items())),
           "green_home_score": s.total if s else None, "score_class": s.classification if s else None}
    for p in PARTS:
        part = next((x for x in s.parts if x.part == p), None) if s else None
        out[f"subscore_{p}"] = None if part is None or part.sub is None else round(part.sub, 3)
        out[f"subscore_{p}_status"] = part.status if part else "unavailable"
    g, e = energy_model.point(home, "gas"), energy_model.point(home, "elec")
    out.update({"baseline_gas_kwh": b.gas_kwh, "baseline_elec_kwh": b.elec_kwh,
                "pred_gas_kwh": g if g is not None else b.gas_kwh, "pred_elec_kwh": e if e is not None else b.elec_kwh,
                "pred_energy_source": "modelled (NEED model)" if (g is not None or e is not None) else b.source,
                "after_gas_kwh": sim.after.gas_total if applied and sim.after else (b.gas_kwh if scenario == "baseline" else None),
                "after_elec_kwh": sim.after.elec_import if applied and sim.after else (b.elec_kwh if scenario == "baseline" else None),
                "saving_gas_kwh": sim.gas_saving_kwh if applied else (0.0 if scenario == "baseline" and b.gas_kwh is not None else None),
                "saving_elec_kwh": sim.elec_saving_kwh if applied else (0.0 if scenario == "baseline" and b.elec_kwh is not None else None),
                "saving_net_kwh": sim.purchased_saving_kwh if applied else (0.0 if scenario == "baseline" and sim.purchased_before_kwh else None),
                "improvement_potential_pct": sim.improvement_potential_pct if applied else None,
                "improvement_potential_status": sim.improvement_potential_status.value if applied else "baseline",
                "co2e_reduction_kg": r.carbon.total_kg if applied else None,
                "recommended_measures": ";".join(x["measure"] for x in (r.recommendation_ranking or [])),
                "install_sequence": ";".join(r.install_sequence or []),
                "sap_after_indicative": (s.epc_change or {}).get("sap_after_indicative") if (s and scenario != "baseline") else None,
                "rating_after_indicative": s.rating_after_indicative if (s and scenario != "baseline") else None,
                "value_uplift_pct_low": r.valuation.low_pct if scenario != "baseline" else None,
                "value_uplift_pct_mid": r.valuation.mid_pct if scenario != "baseline" else None,
                "value_uplift_pct_high": r.valuation.high_pct if scenario != "baseline" else None,
                "value_status": r.valuation.status.value})
    statuses = [s is not None and s.status == ValueStatus.ok, scenario == "baseline" or applied]
    out["prediction_status"] = "ok" if all(statuses) else ("unavailable" if not any(statuses) else "partial")
    return out


def main() -> None:
    t0 = time.time()
    hf = homes_frame()
    test = hf[hf.split == "test"]
    rows = []
    for i, rec in enumerate(test.to_dict("records")):
        h = home_from_row(rec)
        r0 = build(ScenarioRequest(home_id=h.home_id, measures=[], include_packages=False), h)
        r1 = build(ScenarioRequest(home_id=h.home_id, include_packages=False), h)
        rows += [row(r0, "baseline", h), row(r1, "all_feasible", h)]
        if i % 2000 == 0:
            print(f"  {i:,}/{len(test):,} [{time.time()-t0:.0f}s]")
    df = pd.DataFrame(rows)
    assert_no_restricted(df.columns)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT} ({len(df):,} rows, {df.property_id.nunique():,} homes); prediction_status "
          f"{df.prediction_status.value_counts().to_dict()}; models {sorted(registry.shipped_versions())} [{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main()
