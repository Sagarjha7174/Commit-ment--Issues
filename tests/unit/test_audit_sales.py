import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipelines"))
from audit_sales_matches import evaluate, main, parse_correct, wilson  # noqa: E402


def audit(values, methods=None):
    methods = methods or ["exact"] * len(values)
    return pd.DataFrame({"transaction_id": range(len(values)), "match_method": methods, "correct": values})


@pytest.mark.parametrize("v,exp", [("1", True), ("Yes", True), ("y", True), ("TRUE", True), ("0", False), ("no", False),
                                   ("N", False), ("false", False), ("", None), (None, None), (float("nan"), None)])
def test_parse(v, exp):
    assert parse_correct(v) is exp


def test_parse_invalid():
    with pytest.raises(ValueError):
        parse_correct("maybe")


def test_all_filled_passing():
    r = evaluate(audit(["1"] * 48 + ["0"] * 2, ["exact"] * 45 + ["fuzzy"] * 5), 4000)
    assert r["status"] == "audited" and r["precision"] == pytest.approx(0.96)
    assert r["precision_ok"] and r["count_ok"] and r["value_model_enabled_pending_coverage"] is True
    lo, hi = r["wilson_95"]
    assert lo < 0.96 < hi and set(r["by_match_method"]) == {"exact", "fuzzy"}


def test_failing_precision():
    r = evaluate(audit(["y"] * 40 + ["n"] * 10), 4000)
    assert r["precision"] == pytest.approx(0.8) and r["precision_ok"] is False
    assert r["value_model_enabled_pending_coverage"] is False


def test_failing_count():
    r = evaluate(audit(["1"] * 50), 400)
    assert r["precision_ok"] and r["count_ok"] is False and r["value_model_enabled_pending_coverage"] is False


def test_blanks_present(tmp_path):
    r = evaluate(audit(["1"] * 45 + [""] * 5), 4000)
    assert r["status"] == "audit_incomplete" and r["rows_blank"] == 5 and not r["value_model_enabled_pending_coverage"]
    f, s, o = tmp_path / "a.csv", tmp_path / "s.parquet", tmp_path / "g.json"
    audit(["1"] * 45 + [""] * 5).to_csv(f, index=False)
    pd.DataFrame({"match_status": ["linked"] * 600}).to_parquet(s)
    assert main(["--audit", str(f), "--sales", str(s), "--out", str(o)]) == 2


def test_pending(tmp_path):
    f, s, o = tmp_path / "a.csv", tmp_path / "s.parquet", tmp_path / "g.json"
    audit([""] * 50).to_csv(f, index=False)
    pd.DataFrame({"match_status": ["linked"] * 600 + ["unmatched"] * 10}).to_parquet(s)
    assert main(["--audit", str(f), "--sales", str(s), "--out", str(o)]) == 0
    g = json.loads(o.read_text())
    assert g["status"] == "audit_pending" and g["value_model_enabled_pending_coverage"] is False
    assert g["precision"] is None and g["matched_sales_count"] == 600


def test_wilson_known_value():
    lo, hi = wilson(45, 50)
    assert lo == pytest.approx(0.7864, abs=1e-3) and hi == pytest.approx(0.9565, abs=1e-3)
