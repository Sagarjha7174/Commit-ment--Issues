"""Stream members of the EPC bulk zip without unzipping to disk (pyarrow streaming CSV reader)."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv


def members(zip_path: Path, prefix: str) -> list[str]:
    with zipfile.ZipFile(zip_path) as z:
        return sorted(n for n in z.namelist() if n.startswith(prefix) and n.endswith(".csv"))


def header(zip_path: Path, member: str) -> list[str]:
    with zipfile.ZipFile(zip_path) as z, z.open(member) as f:
        return f.readline().decode("utf-8-sig").strip().split(",")


def stream_filter(zip_path: Path, member: str, columns: list[str], key: str, values) -> pa.Table:
    """Read `columns` (all as strings) from one member, keeping rows where `key` is in `values`."""
    cols = [c for c in columns if c in header(zip_path, member)]
    value_set = pa.array(sorted(values), type=pa.string())
    parts = []
    with zipfile.ZipFile(zip_path) as z, z.open(member) as f:
        reader = pacsv.open_csv(
            f,
            read_options=pacsv.ReadOptions(block_size=64 << 20),
            parse_options=pacsv.ParseOptions(newlines_in_values=True),
            convert_options=pacsv.ConvertOptions(include_columns=cols, column_types={c: pa.string() for c in cols},
                                                 strings_can_be_null=True, null_values=[""]),
        )
        for batch in reader:
            mask = pc.is_in(batch.column(key), value_set=value_set)
            parts.append(batch.filter(mask))
    if not parts:
        return pa.table({c: pa.array([], pa.string()) for c in cols})
    t = pa.Table.from_batches(parts)
    for c in columns:  # keep a fixed schema across years
        if c not in t.column_names:
            t = t.append_column(c, pa.nulls(len(t), pa.string()))
    return t.select(columns)
