import json
from pathlib import Path

P = Path(__file__).resolve().parents[2] / "configs" / "score_params.json"


def test_score_params_frozen():
    p = json.loads(P.read_text())
    assert p["version"] == "score-params-v1" and p["split"] == "train"
    i = p["intensity"]
    assert 0 < i["p10"] < i["median"] < i["p90"]
    assert i["n"] > 0 and i["n"] + i["n_excluded"] == i["n_train_total"]
    assert sum(i["excluded_by_reason"].values()) == i["n_excluded"]
