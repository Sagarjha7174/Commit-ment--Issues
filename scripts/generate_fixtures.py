"""Generate the frontend's offline snapshot from the REAL engine (feature/engine-core).

This is a snapshot tool, not a server. Every number in public/fixtures/ is produced by the engine's own
scenario_builder.build() / portfolio code; nothing here calculates anything.

The York parquet is not distributed, so the three public demo homes are rebuilt from configs/demo_homes.json
plus the few non-public EPC fields that tests/fixtures/hand_calc_demo.py documents for them (SUPPLEMENTS below).
The script refuses to write anything unless the engine output reproduces the engine's own hand-calculated
acceptance fixtures (tests/fixtures/scenario_{a,b,c}.json).

Usage (engine venv needs pydantic, pandas, pyarrow):
    python scripts/generate_fixtures.py --engine-dir ../engine-core [--engine-commit <sha>]
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "public" / "fixtures"

# Non-public EPC fields for the demo homes, as documented in tests/fixtures/hand_calc_demo.py
# (A: "cavity walls Poor, roof Very Poor, partial 87%", heating rating used as 80 = Good;
#  B: walls Good, roof N/A with a dwelling above, heating rating 10 = Very Poor, double glazed;
#  C: missing data, only the build year is known).
SUPPLEMENTS = {
    "a_poor_gas_house": {
        "raw_walls_description": "Cavity wall, as built, no insulation (assumed)",
        "raw_roof_description": "Pitched, no insulation (assumed)",
        "multi_glaze_pct": 87.0, "heating_rating": "Good", "age_end": 1975.0,
        "raw_photo_supply": 0.0, "raw_solar_water_heating_flag": "N", "raw_wind_turbine_count": 0,
    },
    "b_flat_loft_solar_infeasible": {
        "raw_walls_description": "Cavity wall, as built, insulated (assumed)",
        "raw_roof_description": "(another dwelling above)",
        "multi_glaze_pct": 100.0, "heating_rating": "Very Poor", "age_end": 2006.0,
        "raw_photo_supply": 0.0, "raw_solar_water_heating_flag": "N", "raw_wind_turbine_count": 0,
    },
    "c_missing_data": {"age_end": 2008.0},
}

MEASURE_ORDER = ["loft_insulation", "cavity_wall", "solid_wall", "double_glazing", "smart_thermostat", "heat_pump", "solar_pv"]

# Assumption presets offered by the UI. Key "default" = engine defaults.
ASSUMPTION_PRESETS = {
    "default": {},
    "impact-low": {"impact_level": "low"},
    "impact-high": {"impact_level": "high"},
    "scop-2.5": {"heat_pump_scop": 2.5},
    "scop-3.5": {"heat_pump_scop": 3.5},
    # Occupancy scenarios ("fewer / more people at home"): the engine's own baseline_scale, the same +/-15%
    # range its sensitivity analysis uses. The engine recalculates; nothing is scaled in the browser.
    "occupancy-low": {"baseline_scale": 0.85},
    "occupancy-high": {"baseline_scale": 1.15},
}

# Budgets offered by the UI. The engine's own package search (services/packages.py, api.search) is rerun
# with each budget: it keeps only packages costing at most that much, then picks the featured plans.
BUDGETS = [1000, 5000, 15000]

# A user meter reading baked in for home A only, so the "user_provided" flow is demonstrable offline.
USER_READING_PRESETS = {"a_poor_gas_house": {"gas_kwh": 18500.0, "elec_kwh": 3400.0}}


def measures_key(measures):
    if measures is None:
        return "engine-default"
    if not measures:
        return "none"
    return "+".join(sorted(measures))


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(b))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-dir", required=True, type=Path)
    ap.add_argument("--engine-commit", default="unknown")
    args = ap.parse_args()
    eng = args.engine_dir.resolve()
    sys.path.insert(0, str(eng))

    import pandas as pd
    from backend.app import config
    from backend.app.schemas.property import SOURCE_COLUMNS, home_from_row
    from backend.app.schemas.scenario import ScenarioRequest
    from backend.app.services import portfolio as portfolio_mod
    from backend.app.services import scenario_builder
    from backend.app.services import packages as packages_mod
    from backend.app.services.baseline import get_baseline
    from backend.app.services.feasibility import assess
    from backend.app.schemas.scenario import Assumptions, UserReading

    demo = json.loads((eng / "configs" / "demo_homes.json").read_text())
    inv = {v: k for k, v in SOURCE_COLUMNS.items()}
    rows, homes = {}, {}
    for h in demo["homes"]:
        row = {c: None for c in SOURCE_COLUMNS}
        row["property_id"], row["split"] = h["home_id"], h["split"]
        for k, v in h["public_fields"].items():
            if k in inv:
                row[inv[k]] = v
        for k, v in SUPPLEMENTS[h["case"]].items():
            row[inv.get(k, k)] = v
        row["postcode"] = h["public_fields"]["postcode_outward"]
        rec = home_from_row(row)
        rec.display_label = h["display_label"]
        rows[h["case"]], homes[h["case"]] = row, rec

    def build(case, measures=None, overrides=None, reading=None):
        h = homes[case]
        req = ScenarioRequest(home_id=h.home_id, measures=measures, assumptions=overrides or {},
                              user_reading=reading, include_packages=True, include_sensitivity=True)
        return scenario_builder.build(req, home=h)

    # ---- parity with the engine's hand-calculated acceptance fixtures ----
    fx = {c: json.loads((eng / "tests" / "fixtures" / f"scenario_{c}.json").read_text())["expect"] for c in "abc"}
    ra = build("a_poor_gas_house")
    ea = fx["a"]
    assert ra.score_before.total == ea["score_before"], ra.score_before.total
    assert close(ra.score_before.raw_total, ea["score_before_raw"])
    assert ra.score_before.classification == ea["class_before"]
    ra_pkg = build("a_poor_gas_house", measures=ea["feasible"])
    assert ra_pkg.score_after.total == ea["score_after"], ra_pkg.score_after.total
    assert close(ra_pkg.simulation.gas_saving_kwh, ea["package_gas_saving_kwh"])
    assert close(ra_pkg.simulation.elec_saving_kwh, ea["package_elec_saving_kwh"])
    assert close(ra_pkg.simulation.improvement_potential_pct, ea["improvement_potential_pct"])
    assert close(ra_pkg.carbon.total_kg, ea["carbon_saving_kg"])
    for m, v in ea["standalone_elec_saving_kwh"].items():
        assert close(ra_pkg.standalone[m]["elec_saving_kwh"], v), m
    states = {f.measure.value: f.state.value for f in ra.feasibility}
    assert [m for m, s in states.items() if s == "infeasible"] == ea["infeasible"], states
    rb, eb = build("b_flat_loft_solar_infeasible"), fx["b"]
    assert rb.score_before.total == eb["score_before"] and rb.score_before.classification == eb["class_before"]
    sb = {f.measure.value: f.state.value for f in rb.feasibility}
    assert sorted(m for m, s in sb.items() if s == "infeasible") == sorted(eb["infeasible"]), sb
    assert {r.measure.value: r.reason_code for r in rb.simulation.measures} == eb["not_estimated"]
    assert rb.simulation.improvement_potential_status.value == eb["improvement_potential_status"]
    rc, ec = build("c_missing_data"), fx["c"]
    assert rc.score_before.status.value == ec["score_status"] and rc.score_before.completeness == ec["completeness"]
    assert rc.baseline.gas_kwh is None and rc.baseline.elec_kwh is None
    assert rc.simulation.improvement_potential_status.value == ec["improvement_potential_status"]
    assert sorted(f.measure.value for f in rc.feasibility if f.state.value == "needs_verification") == sorted(ec["needs_verification"])
    print("parity with hand-calculated fixtures A/B/C: OK")

    # ---- snapshot ----
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "scenarios").mkdir(parents=True)
    (OUT / "shared").mkdir()
    (OUT / "budgets").mkdir()

    def budget_searches(case, overrides, reading, akey, shared_blob):
        """Engine package search per budget. Only featured/fallbacks differ from the unbudgeted search
        (asserted), so the package list is shared and just the picks are stored."""
        h = homes[case]
        a = Assumptions(**(overrides or {}))
        b = get_baseline(h, UserReading(**reading) if reading else None)
        feas = assess(h)
        shared_pk = json.loads(shared_blob)["packages"]
        out = {}
        for budget in BUDGETS:
            ps = packages_mod.search(h, b, feas, a, budget=float(budget)).model_dump(mode="json")
            strip = lambda pk: [{k: v for k, v in x.items() if k != "sensitivity"} for x in pk]  # set only by the full scenario run
            if strip(ps["packages"]) != strip(shared_pk["packages"]):
                raise SystemExit(f"budget search changed the package list for {h.home_id} {akey} {budget}")
            rel = f"budgets/{h.home_id}-{akey}-{budget}.json"
            (OUT / rel).write_text(json.dumps({k: ps[k] for k in ("featured", "fallbacks", "budget_gbp", "threshold_pct")}, separators=(",", ":")))
            out[str(budget)] = rel
        return out
    manifest = {
        "kind": "offline_snapshot",
        "engine_branch": "feature/engine-core", "engine_commit": args.engine_commit,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/generate_fixtures.py",
        "home_inputs": "configs/demo_homes.json public fields + non-public fields documented in tests/fixtures/hand_calc_demo.py",
        "parity": "reproduces tests/fixtures/scenario_{a,b,c}.json (engine hand-calculated acceptance fixtures)",
        "assumption_presets": ASSUMPTION_PRESETS,
        "homes": {},
    }
    total = 0
    for case, h in homes.items():
        base = build(case)
        selectable = [f.measure.value for f in base.feasibility if f.state.value != "infeasible"]
        entry = {"case": case, "selectable": selectable, "variants": {}}
        hid = h.home_id
        (OUT / "scenarios" / hid).mkdir()

        def write(result, akey, mkey, shared_ref):
            nonlocal total
            d = result.model_dump(mode="json")
            shared = {"packages": d.pop("packages"), "sensitivity": d.pop("sensitivity")}
            blob = json.dumps(shared, sort_keys=True)
            if shared_ref.get("blob") is None:
                shared_ref["blob"] = blob
                sh = hashlib.sha256(blob.encode()).hexdigest()[:12]
                shared_ref["path"] = f"shared/{hid}-{akey}-{sh}.json"
                (OUT / shared_ref["path"]).write_text(blob)
            elif shared_ref["blob"] != blob:
                raise SystemExit(f"packages/sensitivity differ across measure sets for {hid} {akey}; cannot dedupe")
            rel = f"scenarios/{hid}/{akey}__{re.sub(r'[^a-z0-9+_-]', '', mkey)}.json"
            (OUT / rel).write_text(json.dumps(d, separators=(",", ":")))
            total += 1
            return rel

        for akey, overrides in ASSUMPTION_PRESETS.items():
            shared_ref: dict = {}
            files = {}
            files[measures_key(None)] = write(build(case, None, overrides), akey, measures_key(None), shared_ref)
            if akey == "default":
                for n in range(len(selectable) + 1):
                    for combo in itertools.combinations(selectable, n):
                        ms = [m for m in MEASURE_ORDER if m in combo]
                        files[measures_key(ms)] = write(build(case, ms, overrides), akey, measures_key(ms), shared_ref)
            else:
                # Every preset also covers the engine's three featured plans, so "choose a plan, then try a
                # what-if" works offline. Arbitrary custom mixes with non-default assumptions need the live engine.
                for fp in (base.packages.featured if base.packages else []):
                    if fp.package_id and fp.package_id != "none":
                        ms = [m for m in MEASURE_ORDER if m in fp.package_id.split("+")]
                        if measures_key(ms) not in files:
                            files[measures_key(ms)] = write(build(case, ms, overrides), akey, measures_key(ms), shared_ref)
            entry["variants"][akey] = {"overrides": overrides, "shared": shared_ref["path"], "scenarios": files,
                                       "budgets": budget_searches(case, overrides, None, akey, shared_ref["blob"])}
        if case in USER_READING_PRESETS:
            reading = USER_READING_PRESETS[case]
            shared_ref = {}
            rel = write(build(case, None, {}, reading), "reading", measures_key(None), shared_ref)
            entry["user_reading"] = {"reading": reading, "shared": shared_ref["path"], "scenarios": {measures_key(None): rel},
                                     "budgets": budget_searches(case, {}, reading, "reading", shared_ref["blob"])}
        manifest["homes"][hid] = entry

    # demo homes list (public fields only)
    (OUT / "demo-homes.json").write_text(json.dumps([
        {"home_id": h["home_id"], "case": h["case"], "display_label": h["display_label"], "why_chosen": h["why_chosen"],
         "rating": h["public_fields"]["rating"], "property_type": h["public_fields"]["property_type"],
         "postcode_outward": h["public_fields"]["postcode_outward"]}
        for h in demo["homes"]], indent=1))

    # portfolio: the engine's real portfolio code, run over the demo subset only
    df = pd.DataFrame(list(rows.values())).set_index("property_id", drop=False)
    portfolio_mod.homes_frame = lambda: df
    portfolio_mod._evaluate.cache_clear()
    pf = portfolio_mod.portfolio(top_n=50)
    pf["data_mode"] = "demo_subset"
    pf["data_note"] = "Engine portfolio code run over the 3 public demo homes only, not the 65,872-home York dataset."
    (OUT / "portfolio.json").write_text(json.dumps(pf, indent=1, default=str))

    # evidence: configs and validation files, verbatim where possible
    cat = config.catalogue()
    smap = config.score_mappings()
    data_md = (eng / "docs" / "DATA.md").read_text()
    sources = []
    for m in re.finditer(r"^### (1\.\d+) (.+?)\n(.*?)(?=^### |^## )", data_md, re.S | re.M):
        sources.append({"id": m.group(1), "title": m.group(2).strip(), "body": m.group(3).strip()})
    model_switch = config.model_switch()
    evidence = {
        "versions": config.versions(),
        "sources": sources,
        "score": {"weights": smap["weights"], "classes": smap["classes"], "missing": smap["missing"],
                  "rating_points": smap["rating_points"],
                  "parts": {k: smap[k] for k in smap["weights"]},
                  "intensity_params": config.score_params()["intensity"]},
        "catalogue": {
            "version": cat["version"],
            "global": cat["global"],
            "measures": [{k: m.get(k) for k in ("id", "label", "impact", "impact_units", "impact_method", "impact_basis",
                                              "target_end_use", "conversion_method", "household_dispersion", "source",
                                              "source_table", "validated", "cost", "dependencies", "applicability_rules")}
                         for m in cat["measures"]],
        },
        "emission_factors": config.emission_factors(),
        "simulator_vs_need": json.loads((eng / "docs" / "validation" / "simulator_vs_need.json").read_text()),
        "value_gate": config.value_gate(),
        "models": {"status": "pending" if model_switch is None else "available", "detail": model_switch},
        "policy_comparison": {"status": "pending",
                              "detail": "Policy A/B/C regret experiment (eval/) has no saved results on the engine branch yet."},
        "llm_evaluation": {"status": "pending",
                           "detail": "The LLM layer is on feature/llm-layer (docs/LLM.md). Its reported results were measured on a fake "
                                     "engine; they are not quoted here until rerun on the real engine and York demo homes."},
    }
    (OUT / "evidence.json").write_text(json.dumps(evidence, indent=1, default=str))
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"wrote {total} scenario files, {size / 1e6:.2f} MB to {OUT}")


if __name__ == "__main__":
    main()
