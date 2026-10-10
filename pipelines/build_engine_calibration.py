"""Data-derived engine calibration -> configs/engine_calibration.json (DECISIONS D15, D21, D22, D23, D28).

Stages (each recorded with its source and n):
1. area_elasticity (D21): beta per fuel from NEED, log(kWh) on log(representative floor area) within
   main-fuel x property type x EPC band cells (fixed effects, so only the floor-area effect is fitted); band reference
   areas = median representative area per NEED floor-area band.
2. reference_floor_area_m2 (D23): median floor area of York TRAIN homes (plausible areas).
3. segment_effects (D15 rev.): for loft, cavity, solid wall and PV, additive EPC band / age / type effects fitted on
   York's joint mix of homes eligible for the measure, so each segment's York-weighted mean adjustment reproduces its
   empirical-Bayes-shrunk NEED contrast (removes the double counting of correlated segments); weighted least squares,
   with the largest remaining mismatch reported.
4. baseline_spread (D28): typical household spread around a NEED cell median, sigma of log(kWh) = median over L1
   cells of (ln q3 - ln q1) / 1.349, per fuel.
5. score params v2 (D21): pipelines/freeze_score_params.py is rerun on the area-scaled baselines.
6. missing_part_priors (D22): mean sub-score of TRAIN homes where the part is observed (renewables split by EPC age).

Usage: .venv/bin/python pipelines/build_engine_calibration.py     (needs data/processed/ and the York build)
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipelines"))

from backend.app import config  # noqa: E402

OUT = config.CONFIGS / "engine_calibration.json"
VERSION = "engine-cal-v1"
SEGMENT_MEASURES = ("loft_insulation", "cavity_wall", "solid_wall", "solar_pv")
BACKFIT_DIMS = ("epc_rating", "property_age", "property_type")


# ---------------- 1. floor-area elasticity (NEED) ----------------

def fit_area_elasticity(need: pd.DataFrame) -> dict:
    """Within-cell OLS slope of log(kWh) on log(representative area). need: NEED rows (need_*.parquet columns)."""
    out = {"method": "fixed-effects OLS: log(kWh) ~ log(floor_area_m2_rep) within main fuel x property type x EPC band",
           "band_reference_area_m2": {}}
    d = need[need.floor_area_m2_rep.notna() & (need.floor_area_m2_rep > 0)].copy()
    d["lx"] = np.log(d.floor_area_m2_rep)
    for fuel, cond in (("gas", (d.gas_status == "metered") & (d.main_heat_gas == 1) & (d.gas_kwh > 0)),
                       ("elec", (d.elec_status == "metered") & (d.elec_kwh > 0))):
        f = d[cond].copy()
        f["ly"] = np.log(f[f"{fuel}_kwh"])
        keys = ["main_heat_gas", "property_type", "epc_band"]
        f["x"] = f.lx - f.groupby(keys).lx.transform("mean")
        f["y"] = f.ly - f.groupby(keys).ly.transform("mean")
        sxx = float((f.x ** 2).sum())
        beta = float((f.x * f.y).sum() / sxx) if sxx > 0 else None
        out[fuel] = None if beta is None else round(beta, 4)
        out[f"n_{fuel}"] = int(len(f))
    for band, g in d.groupby("floor_area_band_code"):
        out["band_reference_area_m2"][str(int(band))] = round(float(g.floor_area_m2_rep.median()), 2)
    return out


# ---------------- 3. backfitted segment effects ----------------

def backfit(segments: pd.DataFrame, targets: dict[str, dict[str, float]]) -> dict:
    """Additive effects a_d(s) whose York-weighted segment means reproduce the NEED segment contrasts.

    NEED deviations are national; under York's joint mix of homes their implied York-wide averages differ between
    dimensions, so they cannot all be matched exactly. Each target is therefore centred on its York-weighted mean
    (contrasts only; the region adjustment sets the York level) and the effects solve, by weighted least squares
    (weights sqrt(n)), mean over homes in s of sum_d' a_d'(s_d') = t_d(s) - mean_York(t_d) for every d, s.
    segments: one row per home, one column per dimension (segment label or None)."""
    dims = [d for d in segments.columns if targets.get(d)]
    params = [(d, s) for d in dims for s in targets[d] if (segments[d] == s).any()]
    if not params:
        return {"residual_max_abs": 0.0}
    onehot = np.column_stack([(segments[d] == s).to_numpy(dtype=float) for d, s in params])
    centred = {}
    for d in dims:
        covered = segments[d].isin(list(targets[d]))
        mean_t = float(segments.loc[covered, d].map(targets[d]).mean()) if covered.any() else 0.0
        centred[d] = {s: t - mean_t for s, t in targets[d].items()}
    rows, rhs, w = [], [], []
    for d, s in params:
        mask = onehot[:, params.index((d, s))] == 1
        rows.append(onehot[mask].mean(axis=0))      # share of segment-s homes in every other segment
        rhs.append(centred[d][s])
        w.append(np.sqrt(mask.sum()))
    A, b, W = np.array(rows), np.array(rhs), np.array(w)
    sol, *_ = np.linalg.lstsq(A * W[:, None], b * W, rcond=None)
    resid = A @ sol - b
    out = {d: {} for d in dims}
    for (d, s), v in zip(params, sol):
        out[d][s] = round(float(v), 8)
    out["residual_max_abs"] = round(float(np.abs(resid).max()), 8)
    return out


def segment_effects(homes: list, assess, impacts) -> dict:
    """homes: HomeRecords. Backfit per measure on homes where the measure is not infeasible."""
    from backend.app.schemas.enums import FeasibilityState, MeasureId
    feas = [{f.measure: f.state for f in assess(h)} for h in homes]
    out = {}
    for mid in SEGMENT_MEASURES:
        table = impacts.shrinkage(mid)
        targets = {d: {s: r["shrunk"] for s, r in table.get(d, {}).items()} for d in BACKFIT_DIMS}
        eligible = [h for h, f in zip(homes, feas) if f[MeasureId(mid)] != FeasibilityState.infeasible]
        if not eligible:
            continue
        seg = pd.DataFrame([{d: impacts.segments_for(h)[d] for d in BACKFIT_DIMS} for h in eligible])
        out[mid] = backfit(seg, targets)
        out[mid]["n_homes"] = len(eligible)
    return out


# ---------------- 4. household spread around a benchmark ----------------

def baseline_spread(bench: pd.DataFrame, min_n: int = 30) -> dict:
    b = bench[(bench.level == "L1_fuel_type_epc_area") & (bench.n >= min_n) & (bench.q1 > 0) & (bench.q3 > 0)]
    out = {"method": "median over NEED L1 cells of (ln q3 - ln q1) / 1.349 (lognormal sigma of household use around the cell median)"}
    for fuel in ("gas", "elec"):
        f = b[b.fuel == fuel]
        out[f"{fuel}_sigma_log"] = round(float(((np.log(f.q3) - np.log(f.q1)) / 1.349).median()), 4) if len(f) else None
        out[f"n_cells_{fuel}"] = int(len(f))
    return out


# ---------------- 6. missing-part priors ----------------

def missing_priors(scored: pd.DataFrame) -> dict:
    """scored: one row per TRAIN home with sub_<part> columns (None when missing) and flag_stale_epc."""
    from backend.app.services.score import PARTS
    out = {}
    for p in PARTS:
        col = scored[f"sub_{p}"].dropna()
        if p == "renewables":
            out[p] = {k: round(float(scored.loc[scored.flag_stale_epc == stale, f"sub_{p}"].dropna().mean()), 3)
                      for k, stale in (("stale_epc", True), ("recent_epc", False))}
        elif len(col):
            out[p] = round(float(col.mean()), 3)
    return out


def _rel(path: Path) -> str:
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def _write(cal: dict) -> None:
    OUT.write_text(json.dumps(cal, indent=1))
    config.engine_calibration.cache_clear()
    config._json.cache_clear()


def main(need_path: Optional[Path] = None):
    from backend.app.data.loaders import homes_frame
    from backend.app.schemas.property import home_from_row
    from backend.app.services import impacts
    from backend.app.services.feasibility import assess
    from backend.app.services.score import score_home

    cal = {"version": VERSION, "built": date.today().isoformat(), "sources": {}}
    proc = ROOT / "data" / "processed"
    need_path = need_path or (proc / "need_4m.parquet" if (proc / "need_4m.parquet").exists() else proc / "need_50k.parquet")
    need = pd.read_parquet(need_path, columns=["floor_area_band_code", "floor_area_m2_rep", "gas_kwh", "elec_kwh",
                                               "gas_status", "elec_status", "main_heat_gas", "property_type", "epc_band"])
    cal["area_elasticity"] = fit_area_elasticity(need)
    cal["sources"]["area_elasticity"] = _rel(need_path)

    df = homes_frame()
    train = df[df.split == "train"]
    areas = train.floor_area_m2[train.floor_area_m2.notna() & ~train.flag_floor_area_implausible.fillna(False).astype(bool)]
    cal["reference_floor_area_m2"] = round(float(areas.median()), 1)

    homes = [home_from_row(r) for r in df.to_dict("records")]
    cal["segment_effects"] = segment_effects(homes, assess, impacts)

    cal["baseline_spread"] = baseline_spread(pd.read_parquet(config.REGION_DIR / "benchmarks.parquet"))
    cal["sources"]["baseline_spread"] = "data/processed/region=york/benchmarks.parquet"
    _write(cal)   # stages 1-4 must be visible to the refreeze and the scoring below

    import freeze_score_params
    freeze_score_params.main()
    config._json.cache_clear()

    rows = []
    for h in (x for x in homes if x.split == "train"):
        s = score_home(h)
        rows.append({"flag_stale_epc": h.flag_stale_epc, **{f"sub_{p.part}": p.sub for p in s.parts}})
    cal["missing_part_priors"] = missing_priors(pd.DataFrame(rows))
    _write(cal)
    print(f"Wrote {_rel(OUT)}")
    print(json.dumps({k: v for k, v in cal.items() if k != "segment_effects"}, indent=1))
    for m, e in cal["segment_effects"].items():
        print(f"  segment effects {m}: n={e.get('n_homes')}")


if __name__ == "__main__":
    main()
