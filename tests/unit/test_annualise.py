import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipelines"))
from annualise import ELEC_PATTERN, GAS_PATTERN, annualise  # noqa: E402


@pytest.mark.parametrize("pattern", [GAS_PATTERN, ELEC_PATTERN])
def test_patterns_sum_to_one(pattern):
    assert abs(sum(pattern.values()) - 1) < 1e-12


@pytest.mark.parametrize("pattern", [GAS_PATTERN, ELEC_PATTERN])
def test_full_year_recovers_total(pattern):
    months = {m: 12000 * s for m, s in pattern.items()}
    val, status = annualise(months, pattern)
    assert val == pytest.approx(12000) and status == "complete"


def test_missing_months_not_zero():
    months = {m: 10000 * s for m, s in GAS_PATTERN.items()}
    months[1] = None          # explicit missing
    del months[7]             # absent key
    val, status = annualise(months, GAS_PATTERN)
    assert val == pytest.approx(10000)  # exact pattern data -> exact recovery
    assert status == "annualised_2_missing"
    # treating missing as zero would have under-estimated:
    assert val > sum(v for v in months.values() if v)


def test_nan_is_missing():
    months = {m: 5000 * s for m, s in ELEC_PATTERN.items()}
    months[3] = float("nan")
    val, status = annualise(months, ELEC_PATTERN)
    assert val == pytest.approx(5000) and status == "annualised_1_missing"


def test_six_missing_ok_seven_unavailable():
    months = {m: 1000 * s for m, s in GAS_PATTERN.items()}
    six = {m: v for m, v in months.items() if m > 6}
    assert annualise(six, GAS_PATTERN)[1] == "annualised_6_missing"
    five = {m: v for m, v in months.items() if m > 7}
    assert annualise(five, GAS_PATTERN) == (None, "unavailable")
    assert annualise({}, GAS_PATTERN) == (None, "unavailable")


def test_zero_consumption_is_valid():
    months = {m: 0.0 for m in range(1, 13)}
    assert annualise(months, GAS_PATTERN) == (0.0, "complete")
