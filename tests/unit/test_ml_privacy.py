"""Privacy guard for ML reads: restricted columns are never loaded; only outward code and sector are derived."""
import json

import pandas as pd
import pytest

from backend.app import config
from backend.app.ml.privacy import (assert_no_restricted, is_restricted, postcode_parts, safe_read_parquet)


def _toy(tmp_path):
    p = tmp_path / "toy.parquet"
    pd.DataFrame({
        "property_id": ["a", "b", "c", "d"],
        "address": ["1 High St", "2 High St", "3 Low Rd", None],
        "raw_address1": ["x", "y", "z", None],
        "postcode": ["YO31 1AB", "yo1 7hh", "YO10  5DD", "bad"],
        "paon": ["1", "2", "3", None],
        "sale_addr": ["s", "t", "u", None],
        "postcode_district": ["YO31", "YO1", "YO10", None],
        "sap_score": [60.0, 70.0, None, 55.0],
    }).to_parquet(p)
    return p


def test_feature_availability_restricted_roles_are_restricted():
    roles = json.loads((config.CONFIGS / "feature_availability.json").read_text())["roles"]
    for col, role in roles.items():
        if role == "restricted_address":
            assert is_restricted(col), col
    for col in ("paon", "saon", "street", "sale_addr", "sale_addr_loc", "epc_address", "address_key", "posttown"):
        assert is_restricted(col)
    for col in ("postcode_outward", "postcode_district", "postcode_sector", "sap_score", "property_id"):
        assert not is_restricted(col)


def test_default_read_drops_every_restricted_column(tmp_path):
    df = safe_read_parquet(_toy(tmp_path))
    assert set(df.columns) == {"property_id", "postcode_district", "sap_score"}


def test_asking_for_a_restricted_column_raises(tmp_path):
    with pytest.raises(ValueError):
        safe_read_parquet(_toy(tmp_path), columns=["property_id", "postcode"])
    with pytest.raises(ValueError):
        safe_read_parquet(_toy(tmp_path), columns=["sale_addr"])


def test_derive_postcode_keeps_only_outward_and_sector(tmp_path):
    df = safe_read_parquet(_toy(tmp_path), columns=["property_id"], derive_postcode=True)
    assert list(df.columns) == ["property_id", "postcode_outward", "postcode_sector"]
    assert df.postcode_outward.tolist() == ["YO31", "YO1", "YO10", None]
    assert df.postcode_sector.tolist() == ["YO31 1", "YO1 7", "YO10 5", None]
    assert_no_restricted(df.columns)


def test_postcode_parts_rejects_malformed_and_missing():
    o, s = postcode_parts(pd.Series(["SW1A 1AA", "", None, "12345", "M1 1AE"]))
    assert o.tolist() == ["SW1A", None, None, None, "M1"]
    assert s.tolist() == ["SW1A 1", None, None, None, "M1 1"]


def test_inventory_never_loads_restricted_columns(tmp_path, monkeypatch):
    import pipelines.ml.inspect_data as insp

    seen = []
    real = insp.safe_read_parquet
    monkeypatch.setattr(insp, "safe_read_parquet", lambda p, columns=None, **k: (seen.extend(columns or []), real(p, columns, **k))[1])
    rows = insp.column_inventory(_toy(tmp_path))
    assert not any(is_restricted(c) for c in seen)
    restricted = {r["column"] for r in rows if r["note"]}
    assert restricted == {"address", "raw_address1", "postcode", "paon", "sale_addr"}
    assert all(r["null_pct"] is None and r["n_distinct"] is None for r in rows if r["note"])
