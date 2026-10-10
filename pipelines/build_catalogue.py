"""Build configs/retrofit_catalogue.json (version cat-v1) from repo files only.

Impacts: NEED 'Impact of measures' 2023 tables in dataset/ (loft, cavity, solid wall, solar);
brief illustrative ranges for glazing and thermostat; heat pump physics with assumed SCOP.
Costs: assessor indicative_cost ranges in the York EPC recommendations (recommendations_long.parquet).

Usage: .venv/bin/python pipelines/build_catalogue.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DS = ROOT / "dataset"
YORK = ROOT / "data" / "processed" / "region=york"
OUT = ROOT / "configs" / "retrofit_catalogue.json"
VERSION = "cat-v3"
SPACE_SHARE = 0.77  # D11: ECUK 2026 U3, space = 77.3% of space+water gas (2021-2025 mean)
WATER_SHARE = 0.23
HEADLINE = DS / "Impact_of_measures_headline_EW_2023.xlsx"
ATTR = {"loft_insulation": "loft", "cavity_wall": "cavity_wall", "solid_wall": "solid_wall", "solar_pv": "solar"}
HEADLINE_ROW = {"loft_insulation": "Loft Insulation", "cavity_wall": "Cavity Wall Insulation",
                "solid_wall": "Solid Wall Insulation", "solar_pv": "Solar PV"}
COST_SINCE = "2022-01-01"  # recent certificates only: older assessor software used older price text


def headline() -> pd.DataFrame:
    t = pd.read_excel(HEADLINE, sheet_name="Table 1", header=3)
    t.columns = ["measure", "savings_shown", "notes", "n", "median_pct", "mean_pct", "median_kwh", "mean_kwh"]
    return t.dropna(subset=["n"]).set_index("measure")


def distribution() -> pd.DataFrame:
    t = pd.read_excel(HEADLINE, sheet_name="Table 3", header=3)
    t.columns = ["measure", "source", "variable", "notes", "n", "mean", "p5", "q1", "median", "q3", "p95"]
    return t[t.variable == "Savings estimate"].set_index("measure")


def segment_table(measure_file: str, table: str) -> dict:
    """Percentage-savings half (columns 0-7) of an attributes table; '[no data]' -> null."""
    raw = pd.read_excel(DS / f"Impact_of_measures_attributes_{measure_file}_EW_2023.xlsx", sheet_name=table, header=None)
    title = str(raw.iloc[0, 0])
    hdr = next(i for i in range(len(raw)) if str(raw.iloc[i, 1]).startswith("Number in"))
    body = raw.iloc[hdr + 1:, :8]
    body.columns = ["segment", "n", "mean", "p5", "q1", "median", "q3", "p95"]
    body = body.dropna(subset=["segment"])
    rows = {}
    for r in body.itertuples():
        def v(x):
            return None if (isinstance(x, str) or pd.isna(x)) else round(float(x), 6)
        rows[str(r.segment).strip()] = {"n": v(r.n), "median_pct": v(r.median), "mean_pct": v(r.mean), "q1": v(r.q1), "q3": v(r.q3),
                                        "status": "observed" if v(r.median) is not None else "unavailable"}
    return {"table": f"{measure_file} {table}: {title}", "segments": rows}


def parse_cost(s: str):
    if not isinstance(s, str):
        return None
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", s)]
    if not nums:
        return None
    return (nums[0] + nums[-1]) / 2 if len(nums) >= 2 else nums[0], len(nums) >= 2, nums[0], nums[-1]


def costs() -> dict:
    r = pd.read_parquet(YORK / "recommendations_long.parquet")
    homes = pd.read_parquet(YORK / "homes.parquet", columns=["certificate_number", "lodgement_date"])
    r = r.merge(homes, on="certificate_number", how="left")
    out = {}
    for m, g in r.groupby("measure"):
        if m == "other":
            continue
        recent = g[g.lodgement_date >= COST_SINCE]
        base, window = (recent, f"certificates lodged >= {COST_SINCE}") if len(recent.dropna(subset=["indicative_cost"])) >= 30 else (g, "all years (too few recent)")
        parsed = base.indicative_cost.map(parse_cost).dropna()
        if len(parsed) == 0:
            out[m] = {"low": None, "mid": None, "high": None, "status": "unavailable", "source": "no indicative_cost values"}
            continue
        mids = np.array([p[0] for p in parsed])
        ranges = int(sum(p[1] for p in parsed))
        out[m] = {
            "low": float(np.percentile(mids, 25)), "mid": float(np.median(mids)), "high": float(np.percentile(mids, 75)),
            "currency": "GBP", "n": int(len(mids)), "n_range_strings": ranges, "n_missing_cost": int(base.indicative_cost.isna().sum()),
            "distinct_cost_strings": int(base.indicative_cost.nunique()),
            "assessor_range_low": float(np.median([p[2] for p in parsed if p[1]])) if ranges else None,
            "assessor_range_high": float(np.median([p[3] for p in parsed if p[1]])) if ranges else None,
            "assessor_range_note": "median lower/upper bound of the assessor's range text; use when p25 = p75 (identical software text)",
            "method": "p25 / median / p75 of the midpoint of each assessor indicative_cost range (single values used as-is)",
            "source": "EPC recommendations indicative_cost, City of York (E06000014), data/processed/region=york/recommendations_long.parquet",
            "window": window, "year": "2022-2026" if window.startswith("cert") else "2008-2026",
            "status": "derived_from_data",
        }
        if len(mids) < 100 or out[m]["distinct_cost_strings"] <= 1:
            out[m]["status"] = "derived_from_data_low_confidence"
            out[m]["note"] = (f"only {len(mids)} values / {out[m]['distinct_cost_strings']} distinct cost text(s); "
                              "the range reflects one software default text, not observed installation prices")
    return out


ECUK_FILE = ROOT / "configs/reference_docs/ECUK_2026_End_Use_tables.xlsx"
ECUK_SOURCE = ("DESNZ Energy Consumption in the UK (ECUK) 2026, End uses data tables, Table U3 (domestic natural gas by end use), "
               "https://www.gov.uk/government/statistics/energy-consumption-in-the-uk-2026 ; local copy configs/reference_docs/ECUK_2026_End_Use_tables.xlsx")


def ecuk_gas_split(years=(2021, 2022, 2023, 2024, 2025)) -> dict:
    r = pd.read_excel(ECUK_FILE, sheet_name="Table U3", header=4)
    r.columns = [str(c).split("\n")[0] for c in r.columns]
    g = r[r.Year.isin(years)].set_index("Year")
    sp, wa, co, tot = (g[f"Natural gas - {k}"].astype(float) for k in ("space heating", "water heating", "cooking", "total"))
    return {"years": list(years), "space": round(float((sp / tot).mean()), 4), "water": round(float((wa / tot).mean()), 4),
            "cooking": round(float((co / tot).mean()), 4), "space_of_heat_water": round(float((sp / (sp + wa)).mean()), 4)}


def main():
    hl, dist = headline(), distribution()
    ecuk = ecuk_gas_split()
    cost = costs()

    def need_impact(mid: str) -> dict:
        row = hl.loc[HEADLINE_ROW[mid]]
        med, mean = float(row.median_pct), float(row.mean_pct)
        return {"low": round(min(med, mean), 6), "mid": round(med, 6), "high": round(max(med, mean), 6)}

    def need_block(mid: str, basis: str, end_use: str, label: str, rules: dict, deps: list) -> dict:
        row, d = hl.loc[HEADLINE_ROW[mid]], dist.loc[HEADLINE_ROW[mid]]
        return {
            "id": mid, "label": label, "applicability_rules": rules,
            "impact": need_impact(mid), "impact_units": "fraction of impact_basis (0.12 = 12%)",
            "impact_method": "mid = NEED headline median % saving; low/high = lower/higher of NEED headline median and mean",
            "impact_basis": basis, "target_end_use": end_use,
            "conversion_method": "none: NEED reports the % of the whole-home annual metered fuel, applied directly to that basis",
            "household_dispersion": {"q1": round(float(d.q1), 6), "q3": round(float(d.q3), 6), "p5": round(float(d.p5), 6),
                                     "p95": round(float(d.p95), 6), "note": "spread of individual-home outcomes, not uncertainty in the mean"},
            "kwh_reference": {"median_kwh": round(float(row.median_kwh), 1), "mean_kwh": round(float(row.mean_kwh), 1), "n": int(row.n)},
            "source": "DESNZ, NEED: Impact of measures, installation year 2023 (England and Wales)",
            "source_table": f"Impact_of_measures_headline_EW_2023.xlsx, Table 1, row '{HEADLINE_ROW[mid]}' ({row.savings_shown}); distribution: Table 3 'Savings estimate'",
            "impact_by_segment": {k: segment_table(ATTR[mid], t) for k, t in
                                  (("epc_rating", "Table 1"), ("property_age", "Table 2"), ("property_type", "Table 3"), ("region", "Table 8"))},
            "validated": True,
            "cost": cost.get(mid, {"low": None, "mid": None, "high": None, "status": "unavailable"}),
            "dependencies": deps, "version": VERSION,
        }

    cat = {
        "version": VERSION,
        "generated_by": "pipelines/build_catalogue.py",
        "global": {
            "boiler_efficiency": {"value": 0.85, "status": "assumption", "note": "seasonal efficiency of an existing gas boiler; used to convert gas kWh to delivered heat"},
            "other_gas_share": {"value": ecuk["cooking"], "status": "published_national_average", "configurable": True,
                                "definition": "share of total household gas NOT used for space or water heating (cooking etc.)",
                                "source": ECUK_SOURCE, "evidence": ecuk,
                                "note": "UK-wide domestic average, not York-specific; mean of 2021-2025"},
            "space_share_of_heat_water_gas": {"value": SPACE_SHARE, "status": "assumption", "configurable": True,
                                              "definition": "share of (space + water heating) gas used for space heating",
                                              "evidence": {"ecuk_2021_2025_mean": ecuk["space_of_heat_water"], "source": ECUK_SOURCE},
                                              "note": "0.77 = ECUK 2021-2025 mean 77.3% rounded to 2 dp (decision D11; cat-v2 used 0.75)"},
            "water_share_of_heat_water_gas": {"value": WATER_SHARE, "status": "assumption", "configurable": True,
                                              "definition": "share of (space + water heating) gas used for water heating; = 1 - space_share_of_heat_water_gas"},
            "heat_pump_scop": {"low": 2.5, "mid": 3.0, "high": 3.5, "status": "assumption",
                               "definition": "seasonal coefficient of performance of an air source heat pump (useful heat / electricity)",
                               "note": "same values as the heat_pump measure impact block; read from here by the engine"},
            "derived": {"space_share_of_total_gas": round(SPACE_SHARE * (1 - ecuk["cooking"]), 6),
                        "formula": "space_share_of_heat_water_gas x (1 - other_gas_share)",
                        "ecuk_space_share_of_total_gas": ecuk["space"]},
            "impact_sign_convention": "saving = baseline - after; positive = reduction",
        },
        "measures": [
            need_block("loft_insulation", "total_gas", "space_heating", "Loft / roof insulation",
                       {"text": "Not a flat/maisonette without its own roof (EPC roof N/A = another dwelling above); roof rating not Good/Very Good",
                        "requires": {"roof_rating_status": "observed", "roof_rating_not_in": ["Good", "Very Good"]},
                        "unknown_if_missing": ["roof_rating"]}, []),
            need_block("cavity_wall", "total_gas", "space_heating", "Cavity wall insulation",
                       {"text": "Built before 2000; cavity walls; walls rating not Good/Very Good",
                        "requires": {"age_end_lt": 2000, "walls_description_regex": "^cavity wall", "walls_rating_not_in": ["Good", "Very Good"]},
                        "unknown_if_missing": ["age_end", "raw_walls_description", "walls_rating"]}, []),
            need_block("solid_wall", "total_gas", "space_heating", "Solid wall insulation (internal or external)",
                       {"text": "Solid masonry walls; walls rating not Good/Very Good",
                        "requires": {"walls_description_regex": "^(solid brick|sandstone|limestone|granite|whinstone|cob)",
                                     "walls_rating_not_in": ["Good", "Very Good"]},
                        "unknown_if_missing": ["raw_walls_description", "walls_rating"]}, []),
            {
                "id": "double_glazing", "label": "Double glazing",
                "applicability_rules": {"text": "Glazing not already double or triple", "requires": {"glazing_not_in": ["double", "triple"]},
                                        "unknown_if_missing": ["glazing"]},
                "impact": {"low": 0.08, "mid": 0.10, "high": 0.12}, "impact_units": "fraction of impact_basis",
                "impact_basis": "space_heat_demand", "target_end_use": "space_heating",
                "conversion_method": "gas saving = impact x space_share_of_heat_water_gas x (1 - other_gas_share) x baseline gas (gas-heated homes); partial glazing scaled by unglazed share",
                "source": "assignment brief illustrative range (Lloyds PS2, section 4)", "source_table": None,
                "validated": False, "cost": cost.get("double_glazing"), "dependencies": [], "version": VERSION,
            },
            {
                "id": "smart_thermostat", "label": "Smart thermostat / zoned heating controls",
                "applicability_rules": {"text": "Controls not already 'smart' (EPC proxy: time and temperature zone control)",
                                        "requires": {"controls_not_in": ["smart"]}, "unknown_if_missing": ["controls"]},
                "impact": {"low": 0.05, "mid": 0.075, "high": 0.10}, "impact_units": "fraction of impact_basis",
                "impact_basis": "space_heat_demand", "target_end_use": "space_heating",
                "conversion_method": "gas saving = impact x space_share_of_heat_water_gas x (1 - other_gas_share) x baseline gas; applied after fabric measures",
                "source": "assignment brief illustrative range (Lloyds PS2, section 4)", "source_table": None,
                "validated": False, "cost": cost.get("smart_thermostat"), "dependencies": [], "version": VERSION,
            },
            {
                "id": "heat_pump", "label": "Air source heat pump",
                "applicability_rules": {"text": "Not already a heat pump; flats (no confirmed outdoor space) get Low suitability",
                                        "requires": {"heating_type_not_in": ["heat_pump"]},
                                        "suitability_low_if": {"property_type_in": ["Flat", "Maisonette"]},
                                        "unknown_if_missing": ["heating_type"]},
                "impact": {"scop_low": 2.5, "scop_mid": 3.0, "scop_high": 3.5}, "impact_units": "seasonal coefficient of performance",
                "impact_basis": "total_gas", "target_end_use": "space_heating_and_hot_water",
                "conversion_method": "heat = (1 - other_gas_share) x gas x boiler_efficiency (space + water); added electricity = heat / SCOP; that gas removed, cooking gas stays. "
                                     "Gas goes down and electricity goes up (negative electricity saving).",
                "source": "assumption: SCOP 3.0 (2.5-3.5)", "source_table": None, "validated": False,
                "cost": cost.get("heat_pump"), "dependencies": ["loft_insulation", "cavity_wall", "solid_wall", "double_glazing"],
                "dependency_note": "apply after fabric measures: heat pump sizing and savings use the post-fabric heat demand",
                "version": VERSION,
            },
            need_block("solar_pv", "total_grid_electricity", "grid_import", "Solar PV panels",
                       {"text": "Not a flat/maisonette; no existing PV", "requires": {"property_type_not_in": ["Flat", "Maisonette"], "solar_pv_not": True},
                        "unknown_if_missing": ["property_type", "solar_pv"]}, []),
        ],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(cat, indent=1, sort_keys=False))
    print(f"Wrote {OUT}")
    for m in cat["measures"]:
        c = m["cost"] or {}
        print(f"{m['id']:18s} impact={m['impact']} basis={m['impact_basis']:22s} validated={m['validated']} "
              f"cost={c.get('low')}/{c.get('mid')}/{c.get('high')} n={c.get('n')} {c.get('status')}")


if __name__ == "__main__":
    main()
