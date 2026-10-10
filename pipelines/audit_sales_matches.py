"""Score the manual sales-match audit and evaluate the value-model go/no-go gate (DECISIONS D10).

Fill the `correct` column of data/processed/region=york/match_audit_sample.csv with 1/0
(yes/no, y/n, true/false; case-insensitive), then run:
    .venv/bin/python pipelines/audit_sales_matches.py

Writes configs/value_gate.json. Outcomes:
- every row blank  -> status "audit_pending", gate closed (exit 0)
- some rows blank  -> status "audit_incomplete", gate closed, error (exit 2)
- invalid values   -> error (exit 2)
- all filled       -> precision, Wilson 95% CI, by-method breakdown, gate decision
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
YORK = ROOT / "data/processed/region=york"
PRECISION_MIN, MATCHED_MIN = 0.90, 500
TRUE = {"1", "yes", "y", "true", "t"}
FALSE = {"0", "no", "n", "false", "f"}


def parse_correct(v) -> bool | None:
    """True/False for a filled cell, None for blank; raises ValueError for anything else."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).strip().lower()
    if s in ("", "nan"):
        return None
    if s in TRUE or s == "1.0":
        return True
    if s in FALSE or s == "0.0":
        return False
    raise ValueError(f"unrecognised value in 'correct': {v!r}")


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def evaluate(audit: pd.DataFrame, matched_sales_count: int) -> dict:
    base = {"thresholds": {"precision_min": PRECISION_MIN, "matched_sales_min": MATCHED_MIN},
            "matched_sales_count": int(matched_sales_count), "n_rows": int(len(audit)),
            "value_model_enabled_pending_coverage": False,
            "coverage_check": "pending (evaluated after value-model training)"}
    if "correct" not in audit.columns:
        raise ValueError("audit file has no 'correct' column")
    parsed = audit["correct"].map(parse_correct)
    filled = parsed.notna()
    base.update(rows_filled=int(filled.sum()), rows_blank=int((~filled).sum()))
    if filled.sum() == 0:
        return base | {"status": "audit_pending", "precision": None, "n_audited": 0,
                       "precision_ok": None, "count_ok": matched_sales_count >= MATCHED_MIN,
                       "note": "audit not filled in; no decision taken"}
    if (~filled).any():
        return base | {"status": "audit_incomplete", "precision": None, "n_audited": int(filled.sum()),
                       "precision_ok": None, "count_ok": matched_sales_count >= MATCHED_MIN,
                       "note": f"{int((~filled).sum())} blank rows; fill every row before the gate is evaluated"}
    k, n = int(parsed.sum()), int(len(parsed))
    precision = k / n
    lo, hi = wilson(k, n)
    by = {}
    if "match_method" in audit.columns:
        for m, g in audit.assign(_c=parsed.astype(bool)).groupby("match_method"):
            kk, nn = int(g._c.sum()), int(len(g))
            by[m] = {"n": nn, "correct": kk, "precision": kk / nn, "wilson_95": list(wilson(kk, nn))}
    precision_ok = precision >= PRECISION_MIN
    count_ok = matched_sales_count >= MATCHED_MIN
    return base | {"status": "audited", "precision": precision, "correct": k, "n_audited": n,
                   "wilson_95": [lo, hi], "by_match_method": by,
                   "precision_ok": precision_ok, "count_ok": count_ok,
                   "value_model_enabled_pending_coverage": bool(precision_ok and count_ok),
                   "uncertainty_note": f"precision from only {n} audited matches: 95% Wilson interval {lo:.3f}-{hi:.3f}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", default=str(YORK / "match_audit_sample.csv"))
    ap.add_argument("--sales", default=str(YORK / "sales_matched.parquet"))
    ap.add_argument("--out", default=str(ROOT / "configs/value_gate.json"))
    a = ap.parse_args(argv)
    audit = pd.read_csv(a.audit, dtype={"correct": str}, keep_default_na=False)
    sales = pd.read_parquet(a.sales, columns=["match_status"])
    matched = int((sales.match_status == "linked").sum())
    try:
        res = evaluate(audit, matched)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    res["audit_file"] = str(Path(a.audit).relative_to(ROOT)) if Path(a.audit).is_relative_to(ROOT) else a.audit
    Path(a.out).write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("status", "rows_filled", "rows_blank", "precision", "matched_sales_count",
                                          "precision_ok", "count_ok", "value_model_enabled_pending_coverage")}, indent=1))
    if res["status"] == "audited":
        print(f"Wilson 95% CI: {res['wilson_95'][0]:.3f} - {res['wilson_95'][1]:.3f}")
        for m, b in res["by_match_method"].items():
            print(f"  {m}: {b['correct']}/{b['n']} = {b['precision']:.3f}")
        print(f"NOTE: precision is measured on only {res['n_audited']} matches, so its uncertainty is wide.")
    if res["status"] == "audit_incomplete":
        print(f"ERROR: {res['rows_blank']} rows of 'correct' are blank; fill all rows and rerun.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
