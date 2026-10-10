import itertools
import json
from pathlib import Path

import pytest

from backend.app import config
from backend.app.schemas.enums import FABRIC, MeasureId as M, ValueStatus
from backend.app.schemas.scenario import Assumptions
from backend.app.services import simulator as simmod
from backend.app.services import units
from backend.app.services.baseline import get_baseline
from backend.app.services.carbon import carbon_change
from backend.app.services.simulator import simulate
from tests.conftest import make_home

CASES = json.loads((Path(__file__).resolve().parents[1] / "reference" / "simulator_cases.json").read_text())["cases"]
ABS = 1e-6


def run(case):
    home = make_home(**case.get("home", {}))
    b = get_baseline(home)
    if "baseline" in case:
        b = b.model_copy(update={"gas_kwh": case["baseline"]["gas"], "elec_kwh": case["baseline"]["elec"]})
    # reference cases are hand-calculated on the catalogue headline impacts; segment adjustment has its own tests
    a = Assumptions(**{"segment_impacts": False, **case.get("assumptions", {})})
    return home, simulate(b, home, case["measures"], a)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_reference_case(case):
    _, s = run(case)
    e = case["expect"]
    for k in ("gas_saving_kwh", "elec_saving_kwh", "improvement_potential_pct"):
        if k in e:
            assert getattr(s, k) == (None if e[k] is None else pytest.approx(e[k], abs=ABS)), k
    if "gas_after" in e:
        assert s.after.gas_total == pytest.approx(e["gas_after"], abs=ABS)
    if "elec_after" in e:
        assert s.after.elec_import == pytest.approx(e["elec_after"], abs=ABS)
    for k in ("gas_space_before", "gas_water_before", "gas_other_before"):
        if k in e:
            assert getattr(s.before, k.replace("_before", "")) == pytest.approx(e[k], abs=ABS)
    if "pv_offset" in e:
        assert s.after.pv_offset == pytest.approx(e["pv_offset"], abs=ABS)
    if "last_step" in e:
        assert s.steps[-1].measure.value == e["last_step"]
    for m, st in e.get("measure_status", {}).items():
        assert next(r for r in s.measures if r.measure.value == m).status.value == st
    for m, rc in e.get("measure_reason", {}).items():
        assert next(r for r in s.measures if r.measure.value == m).reason_code == rc
    if "improvement_potential_status" in e:
        assert s.improvement_potential_status.value == e["improvement_potential_status"]
    if "carbon_total_kg" in e:
        c = carbon_change(s)
        assert c.gas_kg == pytest.approx(e["carbon_gas_kg"], abs=ABS)
        assert c.elec_kg == pytest.approx(e["carbon_elec_kg"], abs=ABS)
        assert c.total_kg == pytest.approx(e["carbon_total_kg"], abs=ABS)
        assert c.gas_kg > 0 and c.elec_kg < 0  # gas falls, electricity rises after a heat pump
    if "sum_of_alone" in e:
        alone = sum(run({**case, "measures": [m]})[1].gas_saving_kwh for m in case["measures"])
        assert alone == pytest.approx(e["sum_of_alone"], abs=ABS) and s.gas_saving_kwh < alone


def test_three_percent_of_total_gas_is_360_kwh():
    c = units.resolve(Assumptions())
    eu = units.decompose(12000.0, 3000.0, True, c)
    kwh, frac = simmod.total_gas_to_space_fraction(eu, 0.03)
    assert kwh == pytest.approx(360.0, abs=ABS) and frac == pytest.approx(360.0 / 8958.18, abs=1e-12)
    after = simmod.reduce_space_heat(eu, frac, c)
    assert eu.gas_total - after.gas_total == pytest.approx(360.0, abs=ABS)


def test_space_reductions_multiply_not_add():
    c = units.resolve(Assumptions())
    eu = units.decompose(12000.0, 3000.0, True, c)
    after = simmod.reduce_space_heat(simmod.reduce_space_heat(eu, 0.15, c), 0.20, c)
    assert 1 - after.gas_space / eu.gas_space == pytest.approx(0.32, abs=1e-12)


def test_fabric_order_does_not_change_total():
    c = units.resolve(Assumptions())
    impacts = {m: config.measure_spec(m.value)["impact"]["mid"] for m in FABRIC}
    totals = []
    for perm in itertools.permutations(FABRIC):
        eu = units.decompose(12000.0, 3000.0, True, c)
        for m in perm:
            _, frac = simmod.total_gas_to_space_fraction(eu, impacts[m])
            eu = simmod.reduce_space_heat(eu, frac, c)
        totals.append(eu.gas_total)
    assert max(totals) - min(totals) < 1e-9


def test_requested_order_is_ignored():
    h = make_home(glazing="single")
    b = get_baseline(h)
    a = simulate(b, h, [M.solar_pv, M.heat_pump, M.double_glazing, M.loft_insulation])
    z = simulate(b, h, [M.loft_insulation, M.double_glazing, M.heat_pump, M.solar_pv])
    assert [s.measure for s in a.steps] == [s.measure for s in z.steps]
    assert a.gas_saving_kwh == z.gas_saving_kwh and a.elec_saving_kwh == z.elec_saving_kwh


def test_removing_a_measure_reverses_its_contribution():
    h = make_home()
    b = get_baseline(h)
    both = simulate(b, h, [M.loft_insulation, M.cavity_wall])
    loft = simulate(b, h, [M.loft_insulation])
    cav_marginal = next(r for r in both.measures if r.measure == M.cavity_wall).gas_saving_kwh
    assert both.gas_saving_kwh - cav_marginal == pytest.approx(loft.gas_saving_kwh, abs=ABS)
    assert simulate(b, h, []).gas_saving_kwh == 0


def test_steps_reconcile_and_cooking_gas_constant():
    h = make_home(glazing="partial", multi_glaze_pct=40.0, controls="timer")
    b = get_baseline(h)
    s = simulate(b, h, list(M))
    assert sum(x.gas_saving_kwh for x in s.steps) == pytest.approx(s.before.gas_total - s.after.gas_total, abs=ABS)
    assert sum(x.elec_saving_kwh for x in s.steps) == pytest.approx(s.before.elec_import - s.after.elec_import, abs=ABS)
    assert s.after.gas_other == s.before.gas_other


def test_unsupported_basis_not_estimated(monkeypatch):
    real = config.measure_spec

    def fake(mid):
        spec = dict(real(mid))
        if mid == "loft_insulation":
            spec["impact_basis"] = "floor_area"
        return spec

    monkeypatch.setattr(simmod.config, "measure_spec", fake)
    h = make_home()
    s = simulate(get_baseline(h), h, [M.loft_insulation])
    r = s.measures[0]
    assert r.status == ValueStatus.not_estimated and r.reason_code == "impact_basis_unsupported" and r.gas_saving_kwh is None


def test_missing_baseline_unavailable():
    h = make_home(baseline_gas_kwh=None, gas_status="unknown_mains_gas")
    s = simulate(get_baseline(h), h, [M.loft_insulation])
    assert s.status == ValueStatus.unavailable and s.gas_saving_kwh is None and s.improvement_potential_pct is None


def test_blocking_flag_makes_improvement_unavailable():
    h = make_home(flag_energy_zero_or_negative=True)
    s = simulate(get_baseline(h), h, [M.loft_insulation])
    assert s.improvement_potential_status == ValueStatus.unavailable and s.improvement_potential_pct is None


def test_impact_level_low_high():
    h = make_home()
    b = get_baseline(h)
    lo, mid, hi = (simulate(b, h, [M.cavity_wall], Assumptions(impact_level=lvl, segment_impacts=False)).gas_saving_kwh for lvl in ("low", "mid", "high"))
    assert lo <= mid <= hi and lo == pytest.approx(0.111382 * 12000, abs=ABS)


def test_improvement_potential_formula():
    h = make_home()
    s = simulate(get_baseline(h), h, [M.loft_insulation], Assumptions(segment_impacts=False))
    assert s.improvement_potential_pct == pytest.approx(100 * 385.404 / 15000, abs=ABS)
