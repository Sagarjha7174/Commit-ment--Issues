"""Read-only access to the built York data. Address columns are never loaded.

Without the York build (data/ is not in git) the loaders serve the three public demo homes from
backend/app/data/demo_homes.py, so the API and the web app run on a fresh clone; data_mode() says which.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from ..config import HOMES_TAGGED
from ..schemas.property import POSTCODE_COLUMN, SOURCE_COLUMNS, HomeRecord, home_from_row
from . import demo_homes


def data_mode() -> str:
    """'york_parquet' when the York build is present, else 'demo_homes' (the three public demo homes only)."""
    return "york_parquet" if HOMES_TAGGED.exists() else "demo_homes"


@lru_cache(maxsize=1)
def homes_frame() -> pd.DataFrame:
    if data_mode() == "demo_homes":
        return demo_homes.demo_frame()
    cols = list(SOURCE_COLUMNS) + [POSTCODE_COLUMN]
    df = pd.read_parquet(HOMES_TAGGED, columns=cols)
    return df.set_index("property_id", drop=False)


def _record(row: dict) -> HomeRecord:
    h = home_from_row(row)
    label = demo_homes.display_labels().get(h.home_id) if data_mode() == "demo_homes" else None
    return h.model_copy(update={"display_label": label}) if label else h


def get_home(home_id: str) -> HomeRecord:
    df = homes_frame()
    if home_id not in df.index:
        raise KeyError(f"unknown home_id {home_id}")
    return _record(df.loc[home_id].to_dict())


def iter_homes(split: str | None = None):
    df = homes_frame()
    if split:
        df = df[df.split == split]
    for row in df.to_dict("records"):
        yield _record(row)
