"""Classify every homes_tagged column -> configs/feature_availability.json.

Roles: feature_ok | label_only | identifier | metadata | deprecated | restricted_address.
label_only = not available at prediction time / would leak a target. restricted_address = EPC
address data (OS/Royal Mail licence): never exposed by the API, never a feature.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/processed/region=york/homes_tagged.parquet"
OUT = ROOT / "configs/feature_availability.json"

IDENTIFIER = {"property_id", "certificate_number", "uprn"}
RESTRICTED = {"address", "postcode", "raw_address1", "raw_address2", "raw_address3", "raw_posttown"}
DEPRECATED = {"epc_predicted_consumption_kwh_m2_primary"}
LABEL_ONLY = {"potential_rating", "potential_sap", "n_recommendations", "has_recommendations",
              "raw_potential_energy_rating", "raw_potential_energy_efficiency"}
METADATA = {"split", "lodgement_date", "baseline_source", "benchmark_cell_level", "data_warnings", "n_data_warnings",
            "improvement_potential_status", "modelled_gas_kwh", "modelled_elec_kwh", "raw_uprn_source",
            "raw_local_authority", "raw_local_authority_label", "raw_region", "raw_inspection_date", "need_region"}
REASONS = {
    "label_only": "assessor recommendations/potential: reference labels, not available for a new home at prediction time",
    "restricted_address": "EPC address data: OS/Royal Mail licence; energy-efficiency purposes only; never returned by the API",
    "deprecated": "use epc_modelled_energy_kwh_m2",
    "identifier": "join key only",
    "metadata": "provenance/status/flags/raw copies or reserved outputs; not model inputs",
    "feature_ok": "observed or benchmark input available when a home is assessed",
}


def role(c: str) -> str:
    if c in IDENTIFIER:
        return "identifier"
    if c in RESTRICTED:
        return "restricted_address"
    if c in DEPRECATED:
        return "deprecated"
    if c in LABEL_ONLY or c.startswith("rec_"):
        return "label_only"
    if (c in METADATA or c.startswith(("prov_", "note_", "flag_", "raw_")) or c.endswith(("_status", "_benchmark_level", "_benchmark_n"))):
        return "metadata"
    return "feature_ok"


def main():
    cols = pq.read_schema(SRC).names
    roles = {c: role(c) for c in cols}
    out = {
        "version": "features-v1", "source": str(SRC.relative_to(ROOT)),
        "roles": roles, "role_reasons": REASONS,
        "other_tables_label_only": {
            "sales_matched.parquet": ["price", "epc_rating_at_sale", "epc_sap_at_sale", "epc_cert_at_sale", "epc_lodged_at_sale"],
            "retrofit_history.parquet": ["all rows with to_date after the home's latest certificate (none by construction)"],
            "recommendations_long.parquet": ["all columns"],
        },
        "counts": pd.Series(roles).value_counts().sort_index().to_dict(),
    }
    OUT.write_text(json.dumps(out, indent=1))
    print(out["counts"])
    print("feature_ok:", [c for c, r in roles.items() if r == "feature_ok"])


if __name__ == "__main__":
    main()
