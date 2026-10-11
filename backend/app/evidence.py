"""Method & Evidence payload for the web app (GET /api/evidence and the frontend's offline snapshot).

Everything is read from the committed configs and generated validation files, verbatim where possible; nothing is
computed here. Blocks without results keep status "pending".
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from . import config

DOCS = config.ROOT / "docs"
VALIDATION = DOCS / "validation"
CATALOGUE_KEYS = ("id", "label", "impact", "impact_units", "impact_method", "impact_basis", "target_end_use",
                  "conversion_method", "household_dispersion", "source", "source_table", "validated", "cost",
                  "dependencies", "applicability_rules")


def _read_json(path: Path) -> Optional[Any]:
    return json.loads(path.read_text()) if path.exists() else None


def data_sources() -> list[dict]:
    """The '### 1.x' source sections of docs/DATA.md."""
    text = (DOCS / "DATA.md").read_text()
    return [{"id": m.group(1), "title": m.group(2).strip(), "body": m.group(3).strip()}
            for m in re.finditer(r"^### (1\.\d+) (.+?)\n(.*?)(?=^### |^## )", text, re.S | re.M)]


def models_block() -> dict:
    """Shipped models with their validation gates and headline validation metrics (configs/model_registry.json)."""
    reg = _read_json(config.CONFIGS / "model_registry.json")
    if not reg:
        return {"status": "pending"}
    models = [{"name": name, "version": m.get("version"), "shipped": bool(m.get("shipped")),
               "gates": m.get("gate") or {}, "headline_val": m.get("headline_val") or {},
               **({"reason": m["reason"]} if m.get("reason") else {})}
              for name, m in sorted(reg.get("models", {}).items())]
    test = _read_json(VALIDATION / "ml_test.json")
    return {"status": "available", "detail": {
        "registry_version": reg.get("version"), "models": models, "model_switch": config.model_switch(),
        "test_scored_once": test is not None,
        "report": "docs/EVALUATION.md (generated from docs/validation/ml_*.json)",
    }}


def llm_block() -> dict:
    """LLM evaluation runs on the real engine (docs/validation/llm_eval_*.json). The template and mocked runs show the
    guardrails, not a live model's answer quality; a live run is reported only when llm_eval_llm.json exists."""
    runs = []
    for mode, label in (("llm", "Live LLM"), ("mock", "Mocked LLM (offline, scripted)"),
                        ("template", "Template explainer (deterministic baseline)")):
        d = _read_json(VALIDATION / f"llm_eval_{mode}.json")
        if d is None:
            continue
        s = d.get("summary", {})
        runs.append({"mode": mode, "label": label, "date": d.get("date"), "n": s.get("n_items"),
                     "groundedness": s.get("groundedness"), "factual_accuracy": s.get("factual_accuracy"),
                     "unsupported_claim_rate": s.get("unsupported_claim_rate"), "whatif_success": s.get("whatif_success"),
                     "refusal_correctness": s.get("refusal_correctness"),
                     "items_all_checks_passed": s.get("items_all_checks_passed"), "targets_met": s.get("targets_met")})
    if not runs:
        return {"status": "pending"}
    live = any(r["mode"] == "llm" for r in runs)
    return {"status": "available", "detail": {
        "targets": {"groundedness": 0.9, "factual_accuracy": 0.9, "unsupported_claim_rate": 0.05},
        "runs": runs, "live_llm_run": live,
        "note": None if live else "No live-LLM run yet: the template and mocked runs show the guardrails, "
                                  "not a live model's answer quality.",
        "report": "docs/LLM_EVALUATION.md",
    }}


def evidence() -> dict:
    cat = config.catalogue()
    smap = config.score_mappings()
    return {
        "versions": {k: str(v) for k, v in config.versions().items() if v is not None},
        "sources": data_sources(),
        "score": {"weights": smap["weights"], "classes": smap["classes"], "missing": smap["missing"],
                  "rating_points": smap["rating_points"], "parts": {k: smap[k] for k in smap["weights"]},
                  "intensity_params": config.score_params()["intensity"]},
        "catalogue": {"version": cat["version"],
                      # the SCOP the engine uses: field evidence (engine_params, D24) overrides the catalogue assumption
                      "global": {**cat["global"], "heat_pump_scop": {**cat["global"]["heat_pump_scop"],
                                                                     **config.catalogue_globals()["heat_pump_scop"],
                                                                     "status": "published_field_evidence (D24)",
                                                                     "note": "Energy Systems Catapult field trials "
                                                                             "(configs/engine_params.json), replacing "
                                                                             "the catalogue assumption 2.5 / 3.0 / 3.5"}},
                      "measures": [{k: m.get(k) for k in CATALOGUE_KEYS} for m in cat["measures"]]},
        "emission_factors": config.emission_factors(),
        "simulator_vs_need": _read_json(VALIDATION / "simulator_vs_need.json"),
        "value_gate": config.value_gate(),
        "energy_prices": config.energy_prices(),
        "grants": config.grants(),
        "finance": config.finance(),
        "models": models_block(),
        "policy_comparison": {"status": "pending",
                              "detail": "The policy A/B/C regret experiment has no saved results yet."},
        "llm_evaluation": llm_block(),
    }
