from backend.app.services.portfolio import portfolio
from tests.conftest import needs_data


@needs_data
def test_portfolio_test_split():
    p = portfolio(top_n=20, split="test")
    s, homes = p["summary"], p["homes"]
    assert s["homes"] == sum(s["count_by_class"].values())
    assert s["flagged_poor_or_very_poor"] == s["count_by_class"].get("Poor", 0) + s["count_by_class"].get("Very poor", 0)
    assert len(homes) == 20 and all(h["classification"] in ("Poor", "Very poor") for h in homes)
    pots = [h["improvement_potential_pct"] for h in homes]
    avail = [x for x in pots if x is not None]
    assert avail == sorted(avail, reverse=True)
    assert pots[: len(avail)] == avail  # unavailable ranked last
    assert all(h["key_issues"] for h in homes)
    for h in homes:
        assert "address" not in h and "postcode" not in h
    assert 0 <= s["share_incomplete_data_pct"] <= 100


@needs_data
def test_portfolio_unavailable_not_zero():
    p = portfolio(top_n=100000, split="test")
    for h in p["homes"]:
        if h["improvement_potential_status"] != "ok":
            assert h["improvement_potential_pct"] is None
