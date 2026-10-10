"""Score every York home with the Green Home Score and write homes_scored.parquet (git-ignored).

Prints the class distribution on the train split and the mean score by EPC band.
Usage: .venv/bin/python pipelines/score_homes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import config  # noqa: E402
from backend.app.data.loaders import homes_frame  # noqa: E402
from backend.app.schemas.property import home_from_row  # noqa: E402
from backend.app.services.score import PARTS, score_home  # noqa: E402


def main():
    df = homes_frame()
    rows = []
    for rec in df.to_dict("records"):
        h = home_from_row(rec)
        s = score_home(h)
        r = {"property_id": h.home_id, "split": h.split, "rating": h.rating, "score_status": s.status.value,
             "score": s.total, "score_raw": s.raw_total, "classification": s.classification,
             "range_low": s.range_low, "range_high": s.range_high, "completeness": s.completeness,
             "missing_parts": ",".join(s.missing_parts), "n_key_issues": len(s.key_issues)}
        for p in s.parts:
            r[f"sub_{p.part}"] = p.sub
        rows.append(r)
    out = pd.DataFrame(rows)
    out["score"] = out["score"].astype("Int64")
    out["score_mappings_version"] = config.score_mappings()["version"]
    config.HOMES_SCORED.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(config.HOMES_SCORED, index=False)
    print(f"Wrote {config.HOMES_SCORED.relative_to(ROOT)} ({len(out):,} homes)")

    tr = out[out.split == "train"]
    order = [c["label"] for c in config.score_mappings()["classes"]]
    print("\nTrain split: class distribution")
    dist = tr.classification.fillna("unavailable").value_counts()
    for k in order + ["unavailable"]:
        n = int(dist.get(k, 0))
        print(f"  {k:17s} {n:6,d}  {100 * n / len(tr):5.1f}%")
    print("\nTrain split: score by EPC band (available scores)")
    g = tr.dropna(subset=["score"]).groupby("rating")["score"].agg(["count", "mean", "min", "median", "max"])
    print(g.round(1).to_string())
    print("\nCompleteness (train):", tr.completeness.value_counts().sort_index().to_dict())
    print("Missing parts (train):", pd.Series(",".join(tr.missing_parts).split(",")).replace("", pd.NA).dropna().value_counts().to_dict())
    print("\nMean sub-score by part (train, non-missing):")
    print(tr[[f"sub_{p}" for p in PARTS]].mean().round(1).to_string())


if __name__ == "__main__":
    main()
