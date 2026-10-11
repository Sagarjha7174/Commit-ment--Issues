"""Every York demo home is explained from the real engine: checker clean, every number grounded, address-free."""
import json

import pytest

from backend.app.llm.explain import explain
from backend.app.llm.payload import assert_address_free, build_payload
from backend.app.schemas.scenario import ScenarioRequest
from backend.app.services.scenario_builder import build
from tests.conftest import DEMO_A, DEMO_B, DEMO_C, needs_data

ADDRESS_WORDS = ("address", "postcode\"", "uprn", "certificate_number", "paon", "saon", "street")


@needs_data
@pytest.mark.parametrize("home_id", [DEMO_A, DEMO_B, DEMO_C])
@pytest.mark.parametrize("uncertainty", [False, True])
def test_demo_home_explained_and_grounded(home_id, uncertainty):
    r = build(ScenarioRequest(home_id=home_id, include_uncertainty=uncertainty))
    res = explain(r, use_llm=False)
    assert res.source == "template" and res.number_check.grounded, res.number_check.unmatched
    text = res.rendered.all_text
    assert "estimate" in text and "None" not in text
    if r.score_before.total is None:
        assert "not available" in text   # demo C: missing data is said, never filled
    pay = build_payload(r)
    assert_address_free(pay)
    blob = json.dumps(pay).lower()
    assert not any(w in blob for w in ADDRESS_WORDS)


@needs_data
def test_demo_a_heat_pump_explains_rising_electricity_and_epc_caveat():
    r = build(ScenarioRequest(home_id=DEMO_A))
    text = explain(r, use_llm=False).rendered.all_text
    assert r.simulation.elec_saving_kwh < 0
    assert "electricity bought from the grid is estimated to rise" in text.lower()
    assert "can lower the EPC (SAP) rating" in text and "association" in text and "benchmark" in text


@needs_data
def test_demo_b_infeasible_explained_and_electric_heating_savings_estimated():
    """Electric flat (D16): savings come off electricity; a heat pump replacing electric heating raises the EPC (D46)."""
    r = build(ScenarioRequest(home_id=DEMO_B))
    text = explain(r, use_llm=False).rendered.all_text
    assert "Not suitable: solar panels" in text
    assert r.simulation.elec_saving_kwh > 0 and "grid electricity is estimated to fall" in text.lower()
    assert r.score_after.epc_change["sap_change"] > 0 and "EPC score goes up" in text
