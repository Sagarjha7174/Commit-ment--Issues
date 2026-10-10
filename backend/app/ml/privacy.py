"""Privacy guard for every ML read (docs/DATA.md §1.6, DECISIONS D31).

Restricted (address) columns are never loaded: the reader selects the allowed columns from the parquet schema before
reading. The full postcode may be read only to derive the outward code ("YO31") and sector ("YO31 1"), and is dropped
in the same call. Nothing here prints or returns a restricted value.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

# restricted_address role in configs/feature_availability.json, plus the sales-table address fields (D31)
RESTRICTED_EXACT = frozenset({
    "address", "address1", "address2", "address3", "raw_address1", "raw_address2", "raw_address3", "raw_posttown",
    "postcode", "posttown", "paon", "saon", "street", "locality", "town", "county", "district",
    "sale_addr", "sale_addr_loc", "epc_address", "address_key", "uprn", "uprn_source", "raw_uprn_source",
})
ALLOWED_LOCATION = frozenset({"postcode_outward", "postcode_district", "postcode_sector"})
POSTCODE_RE = r"^[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}$"   # postcode with spaces removed
SECTOR_RE = r"^[A-Z]{1,2}\d[A-Z\d]? \d$"


def is_restricted(col: str) -> bool:
    c = col.lower()
    if c in ALLOWED_LOCATION:
        return False
    return c in RESTRICTED_EXACT or "addr" in c or "postcode" in c or "posttown" in c


def postcode_parts(pc: pd.Series) -> tuple[pd.Series, pd.Series]:
    """(outward code, sector) from full postcodes; None where the postcode is missing or malformed."""
    s = pc.astype("string").str.upper().str.replace(r"\s+", "", regex=True)
    ok = s.str.match(POSTCODE_RE).fillna(False).astype(bool)
    outward = s.str[:-3].where(ok)
    sector = (outward + " " + s.str[-3]).where(ok)
    return outward.astype(object).where(ok, None), sector.astype(object).where(ok, None)


def safe_read_parquet(path: Path | str, columns: Optional[Iterable[str]] = None,
                      derive_postcode: bool = False) -> pd.DataFrame:
    """Read a parquet file without ever loading a restricted column.

    columns: the wanted columns (default: every allowed column). Asking for a restricted column raises.
    derive_postcode: add postcode_outward / postcode_sector from the full postcode, which is then discarded.
    """
    import pyarrow.parquet as pq

    names = pq.read_schema(path).names
    if columns is None:
        want = [c for c in names if not is_restricted(c)]
    else:
        want = list(columns)
        bad = [c for c in want if is_restricted(c)]
        if bad:
            raise ValueError(f"restricted columns requested: {bad}")
        missing = [c for c in want if c not in names]
        if missing:
            raise KeyError(f"columns not in {Path(path).name}: {missing}")
    df = pd.read_parquet(path, columns=want)
    if derive_postcode:
        if "postcode" not in names:
            raise KeyError(f"{Path(path).name} has no postcode column to derive location from")
        pc = pd.read_parquet(path, columns=["postcode"])["postcode"]
        df["postcode_outward"], df["postcode_sector"] = postcode_parts(pc)
        del pc
    return df


def assert_no_restricted(cols: Iterable[str]) -> None:
    bad = [c for c in cols if is_restricted(c)]
    if bad:
        raise AssertionError(f"restricted columns present: {bad}")
