"""Integrity and leakage checks against the real York data files (same logic as pipelines/check_data.py)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipelines"))
from data_checks import CHECKS  # noqa: E402


@pytest.mark.parametrize("name", list(CHECKS))
def test_check(name):
    ok, detail = CHECKS[name]()
    assert ok, f"{name}: {detail}"
