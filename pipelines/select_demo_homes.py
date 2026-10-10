"""Pick 3 demo homes from the TEST split (deterministic: first by property_id after filtering).

(a) Poor-proxy gas house: EPC rating E/F/G (proxy for score class 'Poor' - score not built yet),
    gas boiler, house/bungalow, walls and roof Poor/Very Poor, single or partial glazing.
(b) Flat where loft and solar are infeasible: flat, roof N/A (another dwelling above), no PV.
(c) Home with missing data: no wall rating; ties broken by most data warnings.

Licence: EPC address data (address1-3, postcode) may be used only for energy-efficiency purposes
and must not be published. Two outputs:
- configs/demo_homes.json (committed): home_id, display label, public fields, outward postcode only,
  engine expectations. No address, no full postcode.
- data/processed/region=york/demo_homes_internal.json (git-ignored, under data/): real address and
  full postcode per home_id, internal_only. Never returned by the API or shown in the UI.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/processed/region=york/homes_tagged.parquet"
PUBLIC_OUT = ROOT / "configs/demo_homes.json"
INTERNAL_OUT = ROOT / "data/processed/region=york/demo_homes_internal.json"
PUBLIC = ["rating", "sap_score", "property_type", "built_form", "age_band", "floor_area_m2", "walls_rating", "walls_rating_status",
          "roof_rating", "roof_rating_status", "glazing", "heating_type", "controls", "solar_pv", "mains_gas",
          "baseline_gas_kwh", "gas_status", "prov_baseline_gas_kwh", "baseline_elec_kwh", "elec_status", "prov_baseline_elec_kwh",
          "benchmark_cell_level", "epc_age_years", "improvement_potential_status"]
LETTERS = {"a_poor_gas_house": "A", "b_flat_loft_solar_infeasible": "B", "c_missing_data": "C"}


def clean(v):
    if isinstance(v, (list, tuple)):
        return list(v)
    if hasattr(v, "tolist") and not isinstance(v, str):
        v = v.tolist()
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
        return None
    if isinstance(v, pd.Timestamp):
        return v.date().isoformat()
    return v


def describe(r) -> str:
    form = (r.built_form or "").lower().replace("-", " ")
    kind = (r.property_type or "home").lower()
    return f"{r.age_band or 'unknown-age'} {form + ' ' if form and kind != 'flat' else ''}{kind}".strip()


def expectations(case: str, r) -> list[str]:
    e = []
    if r.improvement_potential_status == "unavailable":
        e.append("improvement potential must be reported as 'unavailable' (no division by a missing/zero baseline)")
    if r.gas_status == "no_mains_gas":
        e.append("baseline gas is 0 kWh with status no_mains_gas (observed, not missing); gas-based savings and the "
                 "gas-to-heat-pump conversion do not apply; any heat-pump case must start from electric heating")
    if r.heating_type == "electric":
        e.append("electrically heated: savings from fabric measures fall on electricity, not gas")
    if pd.isna(r.baseline_gas_kwh) and r.gas_status != "no_mains_gas":
        e.append(f"baseline gas unavailable (status {r.gas_status}); do not substitute 0")
    if pd.isna(r.baseline_elec_kwh):
        e.append(f"baseline electricity unavailable (status {r.elec_status}); do not substitute 0")
    if pd.isna(r.heating_type):
        e.append("no heating description: heating sub-score and heat-pump feasibility are unknown, not 'no heating'")
    if r.roof_rating_status == "not_applicable":
        e.append("roof N/A (another dwelling above): loft insulation infeasible")
    if r.property_type in ("Flat", "Maisonette"):
        e.append("flat: solar PV infeasible; heat pump suitability Low (outdoor space unconfirmed)")
    if pd.isna(r.walls_rating):
        e.append(f"wall rating missing (status {r.walls_rating_status}): wall measures and the insulation sub-score must be flagged as uncertain")
    if case == "a_poor_gas_house":
        e.append("expected class Poor or Very poor once the score is built (EPC E is only a proxy); fabric measures before heat pump")
    return e


def main():
    t = pd.read_parquet(SRC)
    t = t[t.split == "test"].sort_values("property_id")
    fresh = ~t.flag_stale_epc
    a = t[t.rating.isin(["E", "F", "G"]) & t.heating_type.eq("gas_boiler") & t.property_type.isin(["House", "Bungalow"])
          & t.walls_rating.isin(["Poor", "Very Poor"]) & t.roof_rating.isin(["Poor", "Very Poor"])
          & t.glazing.isin(["single", "partial"]) & t.improvement_potential_status.eq("computable") & fresh]
    b = t[t.property_type.eq("Flat") & t.roof_rating_status.eq("not_applicable") & t.solar_pv.eq(False)
          & t.improvement_potential_status.eq("computable") & fresh]
    c = t[t.walls_rating.isna()].sort_values(["n_data_warnings", "property_id"], ascending=[False, True])
    picks = [("a_poor_gas_house", a, "EPC {rating} used as proxy for 'Poor' class (score not built yet); gas boiler; walls and roof rated "
                                     "poor; {glazing} glazing. {n} test homes matched; first by property_id."),
             ("b_flat_loft_solar_infeasible", b, "Flat with another dwelling above (roof N/A) so loft insulation is infeasible; flats are "
                                                 "excluded from solar PV. {n} test homes matched; first by property_id."),
             ("c_missing_data", c, "No wall rating ({wstat}); data warnings: {warn}. {n} test homes lack a wall rating; most warnings first.")]
    out, internal = [], []
    md = ["# Demo homes (TEST split)\n",
          "Selected by `pipelines/select_demo_homes.py`. 'Poor' uses EPC rating E/F/G as a proxy because the Green Home Score is not built yet.\n",
          "Addresses and full postcodes are **not shown**: EPC address data may only be used for energy-efficiency purposes and must not be "
          "published (see docs/DATA.md). Homes are identified by label and `home_id` (= property_id: UPRN or address hash).\n"]
    for key, df, why in picks:
        assert len(df), key
        r = df.iloc[0]
        label = f"Demo home {LETTERS[key]}, {describe(r)}, York"
        pub = {k: clean(r[k]) for k in PUBLIC}
        pub["postcode_outward"] = str(r.postcode).split(" ")[0] if isinstance(r.postcode, str) else None
        pub["data_warnings"] = list(r.data_warnings)
        rec = {
            "home_id": r.property_id, "case": key, "display_label": label, "split": "test",
            "why_chosen": why.format(rating=r.rating, glazing=r.glazing, n=len(df), wstat=r.walls_rating_status,
                                     warn=list(r.data_warnings) or "none"),
            "public_fields": pub,
            "engine_expectations": expectations(key, r),
        }
        internal.append({"home_id": r.property_id, "display_label": label, "internal_only": True,
                         "address": clean(r.address), "postcode": clean(r.postcode)})
        out.append(rec)
        md.append(f"## {label}\n\n`home_id`: `{rec['home_id']}`. Case `{key}`. {rec['why_chosen']}\n\n| Field | Value |\n|---|---|")
        md += [f"| {k} | {v} |" for k, v in pub.items()]
        md.append("\n**Engine expectations**\n")
        md += [f"- {e}" for e in rec["engine_expectations"]]
        md.append("")
    doc = {"split": "test",
           "licence_note": "Public, committed file: no addresses or full postcodes. Real addresses are in the git-ignored "
                           "data/processed/region=york/demo_homes_internal.json (internal_only).",
           "homes": out}
    PUBLIC_OUT.write_text(json.dumps(doc, indent=1, default=str))
    INTERNAL_OUT.write_text(json.dumps({
        "internal_only": True,
        "note": "EPC address data (OS/Royal Mail licence): energy-efficiency purposes only; never commit, never return from the API or show in the UI",
        "homes": internal}, indent=1, default=str))
    (ROOT / "docs/DEMO_HOMES.md").write_text("\n".join(md))
    for r in out:
        print(r["display_label"], "|", r["home_id"], "|", r["public_fields"]["postcode_outward"], "|", len(r["engine_expectations"]), "expectations")


if __name__ == "__main__":
    main()
