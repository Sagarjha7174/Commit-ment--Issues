"""Read-only access to the built York data. Address columns are never loaded."""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from ..config import HOMES_TAGGED
from ..schemas.property import POSTCODE_COLUMN, SOURCE_COLUMNS, HomeRecord, home_from_row


@lru_cache(maxsize=1)
def homes_frame() -> pd.DataFrame:
    cols = list(SOURCE_COLUMNS) + [POSTCODE_COLUMN]
    df = pd.read_parquet(HOMES_TAGGED, columns=cols)
    return df.set_index("property_id", drop=False)


def get_home(home_id: str) -> HomeRecord:
    df = homes_frame()
    if home_id not in df.index:
        raise KeyError(f"unknown home_id {home_id}")
    return home_from_row(df.loc[home_id].to_dict())


def iter_homes(split: str | None = None):
    df = homes_frame()
    if split:
        df = df[df.split == split]
    for row in df.to_dict("records"):
        yield home_from_row(row)
