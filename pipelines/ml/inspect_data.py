"""M0: schema-only inventory of the tables the ML phase uses -> docs/validation/ml_data_inventory.txt.

Per column: dtype, null %, number of distinct values. Restricted (address) columns are listed by name only and never
loaded (backend/app/ml/privacy.py). The checks section prints counts and category labels of low-cardinality coded
columns only (splits, statuses, field names), never row values.

Usage: .venv/bin/python pipelines/ml/inspect_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.ml.privacy import SECTOR_RE, is_restricted, safe_read_parquet  # noqa: E402

PROC = ROOT / "data" / "processed"
YORK = PROC / "region=york"
OUT = ROOT / "docs" / "validation" / "ml_data_inventory.txt"
OUTWARD_RE = r"^[A-Z]{1,2}\d[A-Z\d]?$"

TABLES = {
    "homes_tagged": YORK / "homes_tagged.parquet",
    "epc_certs_all": YORK / "epc_certs_all.parquet",
    "retrofit_history": YORK / "retrofit_history.parquet",
    "sales_matched": YORK / "sales_matched.parquet",
    "need_4m": PROC / "need_4m.parquet",
    "need_50k": PROC / "need_50k.parquet",
    "benchmarks": YORK / "benchmarks.parquet",
}


def _nunique(s: pd.Series) -> int:
    try:
        return int(s.nunique(dropna=True))
    except TypeError:   # list / dict cells
        return int(s.dropna().astype(str).nunique())


def column_inventory(path: Path) -> list[dict]:
    """One row per column. Restricted columns: name and 'restricted, not loaded' only."""
    schema = pq.read_schema(path)
    n = pq.read_metadata(path).num_rows
    rows = []
    for field in schema:
        if is_restricted(field.name):
            rows.append({"column": field.name, "dtype": str(field.type), "null_pct": None, "n_distinct": None,
                         "note": "restricted, not loaded"})
            continue
        s = safe_read_parquet(path, columns=[field.name])[field.name]   # one column at a time bounds memory
        rows.append({"column": field.name, "dtype": str(s.dtype), "null_pct": round(100.0 * s.isna().mean(), 2) if n else 0.0,
                     "n_distinct": _nunique(s), "note": ""})
        del s
    return rows


def format_table(name: str, path: Path, rows: list[dict]) -> str:
    n = pq.read_metadata(path).num_rows
    out = [f"## {name}  ({path.relative_to(ROOT)}; {n:,} rows, {len(rows)} columns)",
           f"{'column':48s} {'dtype':24s} {'null %':>8s} {'distinct':>10s}  note"]
    for r in rows:
        nul = "" if r["null_pct"] is None else f"{r['null_pct']:.2f}"
        nd = "" if r["n_distinct"] is None else f"{r['n_distinct']:,}"
        out.append(f"{r['column']:48s} {r['dtype'][:24]:24s} {nul:>8s} {nd:>10s}  {r['note']}")
    return "\n".join(out)


def _counts(s: pd.Series) -> str:
    vc = s.astype(object).where(s.notna(), "<null>").value_counts()
    return ", ".join(f"{k}={v:,}" for k, v in vc.items())


def checks() -> list[str]:
    """Assumption checks from the plan. Counts and coded category labels only."""
    out = ["## Plan assumption checks (counts only)"]
    h = safe_read_parquet(TABLES["homes_tagged"], columns=["property_id", "split", "rec_heat_pump", "sap_score"],
                          derive_postcode=True)
    out.append(f"homes_tagged split: {_counts(h.split)}")
    out.append(f"homes_tagged derived postcode_outward: {h.postcode_outward.notna().sum():,} non-null, "
               f"{h.postcode_outward.nunique()} distinct; postcode_sector {h.postcode_sector.nunique()} distinct")
    out.append(f"homes_tagged rec_heat_pump positives: {int(h.rec_heat_pump.fillna(0).sum())}")

    c = safe_read_parquet(TABLES["epc_certs_all"], columns=["property_id", "certificate_number", "c_sap_score",
                                                            "transaction_type", "lodgement_date"])
    c = c.merge(h[["property_id", "split"]], on="property_id", how="left")
    out.append("epc_certs_all has no split column: split joined from homes_tagged on property_id")
    out.append(f"epc_certs_all certificates by home split: {_counts(c.split)}")
    out.append(f"epc_certs_all certificates per home: max {c.groupby('property_id').size().max()}, "
               f"homes with >1 certificate {(c.groupby('property_id').size() > 1).sum():,}")
    sap = pd.to_numeric(c.c_sap_score, errors="coerce")
    out.append(f"epc_certs_all c_sap_score: missing {sap.isna().sum():,}, outside 1-110 {((sap < 1) | (sap > 110)).sum():,}")
    yr = pd.to_datetime(c.lodgement_date, errors="coerce").dt.year
    out.append(f"epc_certs_all lodgement year range: {int(yr.min())}-{int(yr.max())}")
    out.append(f"epc_certs_all transaction_type distinct: {c.transaction_type.nunique()}")

    r = safe_read_parquet(TABLES["retrofit_history"])
    out.append(f"retrofit_history fields: {_counts(r.field)}")

    s = safe_read_parquet(TABLES["sales_matched"], columns=["match_status", "epc_rating_at_sale_status", "split",
                                                            "postcode_district", "postcode_sector", "sale_date",
                                                            "new_build", "tenure", "property_type"])
    out.append(f"sales_matched match_status: {_counts(s.match_status)}")
    out.append(f"sales_matched epc_rating_at_sale_status: {_counts(s.epc_rating_at_sale_status)}")
    out.append(f"sales_matched split: {_counts(s.split)}")
    out.append(f"sales_matched postcode_district outward-code format: {s.postcode_district.astype('string').str.match(OUTWARD_RE).sum():,}"
               f"/{s.postcode_district.notna().sum():,}; postcode_sector sector format: "
               f"{s.postcode_sector.astype('string').str.match(SECTOR_RE).sum():,}/{s.postcode_sector.notna().sum():,}")
    d = pd.to_datetime(s.sale_date, errors="coerce")
    out.append(f"sales_matched sale months: {d.min():%Y-%m} to {d.max():%Y-%m}")
    out.append(f"sales_matched new_build: {_counts(s.new_build)}; tenure: {_counts(s.tenure)}; "
               f"property_type: {_counts(s.property_type)}")
    out.append("sales_matched has no PPD category column: ppd.parquet keeps category A only (docs/DATA.md 1.4)")

    n = safe_read_parquet(TABLES["need_4m"], columns=["split", "region_code", "gas_status", "elec_status", "main_heat_gas"])
    out.append(f"need_4m split: {_counts(n.split)}")
    out.append(f"need_4m Yorkshire and The Humber (E12000003): {(n.region_code == 'E12000003').sum():,}")
    out.append(f"need_4m gas_status: {_counts(n.gas_status)}; elec_status: {_counts(n.elec_status)}")
    return out


def main() -> None:
    parts = ["ML data inventory (schema only; restricted address columns listed by name, never loaded)", ""]
    for name, path in TABLES.items():
        if not path.exists():
            parts += [f"## {name}: {path.relative_to(ROOT)} not present", ""]
            continue
        parts += [format_table(name, path, column_inventory(path)), ""]
        print(f"inventoried {name}")
    parts += checks()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
