"""Address-free export of the tables the ML phase needs -> ml_data_export.zip (share this file, nothing else).

Removes every licence-restricted address field (EPC address lines, full postcodes, Land Registry PAON/SAON/street,
matched address strings, the audit sample). Full postcodes are replaced by the outward code (e.g. "YO31"); a separate
postcode_sector column keeps outward + first inward digit (e.g. "YO31 1"). UPRN-based property ids and certificate
numbers are kept: they are Open Government Licence fields (docs/DATA.md 1.1) and are needed to join the tables.
The script refuses to write the zip if any forbidden column survives.

Usage: .venv/bin/python pipelines/ml/export_for_review.py [--need-rows 1000000]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
YORK = PROC / "region=york"
OUT = ROOT / "ml_data_export.zip"

FORBIDDEN = {
    "address", "address1", "address2", "address3", "raw_address1", "raw_address2", "raw_address3", "raw_posttown",
    "posttown", "paon", "saon", "street", "locality", "town", "address_key", "sale_addr", "sale_addr_loc", "epc_address",
    "uprn", "uprn_source", "raw_uprn_source",
}
POSTCODE_COLS = {"postcode"}


def outward(pc: pd.Series) -> pd.Series:
    return pc.astype("string").str.strip().str.upper().str.split().str[0]


def sector(pc: pd.Series) -> pd.Series:
    s = pc.astype("string").str.strip().str.upper().str.split()
    return (s.str[0] + " " + s.str[1].str[0]).where(s.str.len() >= 2)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop(columns=[c for c in df.columns if c in FORBIDDEN], errors="ignore")
    for c in POSTCODE_COLS & set(df.columns):
        df["postcode_sector"] = sector(df[c])
        df[c] = outward(df[c])     # outward code only, so the engine loader still derives postcode_outward
    left = FORBIDDEN & set(df.columns)
    assert not left, f"forbidden columns survived: {left}"
    if "postcode" in df.columns:
        assert df["postcode"].dropna().str.contains(" ").sum() == 0, "full postcodes survived"
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--need-rows", type=int, default=1_000_000, help="rows sampled from need_4m (stratified by split)")
    args = ap.parse_args()
    tables = {
        "homes_tagged.parquet": YORK / "homes_tagged.parquet",
        "epc_certs_all.parquet": YORK / "epc_certs_all.parquet",
        "retrofit_history.parquet": YORK / "retrofit_history.parquet",
        "sales_matched.parquet": YORK / "sales_matched.parquet",
        "benchmarks.parquet": YORK / "benchmarks.parquet",
        "need_50k.parquet": PROC / "need_50k.parquet",
    }
    tmp = ROOT / "tmp_ml_export"
    tmp.mkdir(exist_ok=True)
    manifest = {}
    for name, src in tables.items():
        if not src.exists():
            print(f"skip {name}: not found")
            continue
        df = clean(pd.read_parquet(src))
        df.to_parquet(tmp / name, index=False)
        manifest[name] = {"rows": len(df), "columns": list(df.columns)}
        print(f"{name}: {len(df):,} rows, {len(df.columns)} columns")
    n4 = PROC / "need_4m.parquet"
    if n4.exists():
        need = pd.read_parquet(n4)
        frac = min(1.0, args.need_rows / len(need))
        samp = need.groupby("split", group_keys=False).sample(frac=frac, random_state=42)
        clean(samp).to_parquet(tmp / "need_sample.parquet", index=False)
        manifest["need_sample.parquet"] = {"rows": len(samp), "columns": list(samp.columns), "sampled_from": len(need)}
        print(f"need_sample.parquet: {len(samp):,} rows sampled from need_4m")
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1))
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(tmp.iterdir()):
            z.write(f, f.name)
            f.unlink()
    tmp.rmdir()
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]
    print(f"\nWrote {OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB, sha256 {digest}). Upload this file only.")


if __name__ == "__main__":
    sys.exit(main())
