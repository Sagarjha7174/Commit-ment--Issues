"""Heating share of electricity for electrically heated homes (DECISIONS D16) -> configs/electric_heating_split.json.

NEED gives annual metered electricity for gas-heated and non-gas-heated homes in the same benchmark cells
(data/processed/region=york/benchmarks.parquet, built by pipelines/build_region.py step 6). Electricity of a
gas-heated home is lights, appliances and cooking; a non-gas-heated home in the same cell uses that plus its heating:

    share = 1 - median elec (gas-heated) / median elec (not gas-heated)      (clipped to [0, 0.9])

Cells: property type x EPC band (L2), falling back to EPC band (L3), then all homes (n-weighted). Both medians need
>= MIN_N homes. "Not gas-heated" also contains oil/LPG/solid-fuel homes whose heating is not electric, so the share is
conservative (an underestimate for direct electric homes). The engine applies it only to heating_type "electric".
Usage: .venv/bin/python pipelines/build_electric_heating_split.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import config  # noqa: E402

BENCH = config.REGION_DIR / "benchmarks.parquet"
OUT = config.CONFIGS / "electric_heating_split.json"
VERSION = "elec-split-v1"
MIN_N = 30
MAX_SHARE = 0.9


def _share(gas_med: float, notgas_med: float) -> float:
    return min(max(1 - gas_med / notgas_med, 0.0), MAX_SHARE) if notgas_med > 0 else None


def _pair(df: pd.DataFrame, keys: list[str]) -> dict:
    e = df[(df.fuel == "elec") & (df.n >= MIN_N)]
    g = e[e.need_main_fuel == 1].set_index(keys)
    o = e[e.need_main_fuel == 2].set_index(keys)
    out = {}
    for k in g.index.intersection(o.index):
        rg, ro = g.loc[k], o.loc[k]
        out[k] = {"share": _share(float(rg["median"]), float(ro["median"])), "elec_gas_heated_kwh": float(rg["median"]),
                  "elec_not_gas_heated_kwh": float(ro["median"]), "n_gas_heated": int(rg["n"]), "n_not_gas_heated": int(ro["n"])}
    return out


def build(bench: pd.DataFrame) -> dict:
    shares: dict[str, dict] = {}
    l2 = bench[bench.level == "L2_fuel_type_epc"]
    for (ptype, band), row in _pair(l2, ["need_property_type", "need_epc_band"]).items():
        shares[f"{ptype}|{band}"] = {**row, "level": "type x EPC band"}
    l3 = bench[bench.level == "L3_fuel_epc"]
    l3_pairs = _pair(l3, ["need_epc_band"])
    for band, row in l3_pairs.items():
        shares[f"*|{band}"] = {**row, "level": "EPC band"}
    if l3_pairs:
        rows = list(l3_pairs.values())
        n = sum(r["n_not_gas_heated"] for r in rows)
        g = sum(r["elec_gas_heated_kwh"] * r["n_not_gas_heated"] for r in rows) / n
        o = sum(r["elec_not_gas_heated_kwh"] * r["n_not_gas_heated"] for r in rows) / n
        shares["*|*"] = {"share": _share(g, o), "elec_gas_heated_kwh": g, "elec_not_gas_heated_kwh": o,
                         "n_not_gas_heated": n, "level": "all homes (n-weighted over EPC bands)"}
    return {"version": VERSION, "built": date.today().isoformat(), "source": str(BENCH.relative_to(ROOT)),
            "method": "share = 1 - median elec of gas-heated homes / median elec of non-gas-heated homes, same NEED cell; "
                      f"cells need >= {MIN_N} homes on both sides; clipped to [0, {MAX_SHARE}]",
            "shares": shares,
            "caveats": ["non-gas-heated NEED homes include oil/LPG/solid fuel, so the share is conservative for direct electric homes",
                        "regional benchmarks (Yorkshire and The Humber), not this home's meter (D6)",
                        "space/water split of the heating share uses the gas split (assumption)"]}


def main():
    bench = pd.read_parquet(BENCH)
    out = build(bench)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(out['shares'])} cells)")
    for k, v in sorted(out["shares"].items()):
        print(f"  {k:24s} share {v['share']:.3f}  gas-heated {v['elec_gas_heated_kwh']:7.0f}  not gas {v['elec_not_gas_heated_kwh']:7.0f}")


if __name__ == "__main__":
    main()
