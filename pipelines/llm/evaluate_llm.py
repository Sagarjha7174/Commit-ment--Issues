"""LLM evaluation on the held-out question set (eval/llm_eval_set.json), end to end through the FastAPI app.

Metrics (targets from the brief: groundedness >= 90%, factual accuracy >= 90%, unsupported-claim rate < 5%):
- groundedness: share of numbers in the answers that match an engine value (numbers.check_numbers, micro average);
- factual accuracy: share of cited values (the numbers shown, by fact key) equal to an engine value recomputed
  independently (a fresh scenario_builder.build of the same request; what-if differences from the two results),
  with the displayed figure consistent with that value;
- unsupported-claim rate: share of answer sentences that carry a number not matching any engine value;
- what-if success: the right outcome, the right ScenarioRequest change (fields compared), the engine rerun with a
  new scenario id (or correctly not rerun), the right measures added / removed / blocked;
- refusal correctness: refused exactly when the item expects a refusal (out of scope, invalid request);
- content checks: per-item regexes (e.g. electricity rising, "not available" for missing data).

Modes: --mode llm (real provider from environment keys; the reported run), --mode template (deterministic baseline,
no network), --mode mock (scripted fake LLM: exercises the LLM path, checker, patching and number check offline).

Usage: .venv/bin/python pipelines/llm/evaluate_llm.py [--mode llm|template|mock]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.llm import client as client_mod  # noqa: E402
from backend.app.llm import service  # noqa: E402
from backend.app.llm.numbers import _forms, _parse  # noqa: E402
from backend.app.llm.payload import build_payload  # noqa: E402
from backend.app.schemas.scenario import ScenarioRequest  # noqa: E402
from backend.app.services.scenario_builder import build  # noqa: E402

EVAL_SET = ROOT / "eval" / "llm_eval_set.json"
OUT_DIR = ROOT / "docs" / "validation"
TARGETS = {"groundedness": 0.90, "factual_accuracy": 0.90, "unsupported_claim_rate": 0.05}
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")


class MockLLM:
    """Scripted stand-in for a provider: writes placeholder prose (and one invented number, which the checker must
    drop) for explanations, and reads what-if questions with the keyword parser."""

    def __init__(self):
        self.settings = client_mod.LLMSettings(providers=("mock",), enabled=True, use_cache=False)
        self.calls = 0

    def structured(self, *, system, user, schema, role="explain", max_tokens=0, purpose=""):
        from backend.app.llm.claims import ExplanationText, WhatIfParse, WhatIfText
        from backend.app.llm.whatif import keyword_parse
        self.calls += 1
        keys = set(re.findall(r"^([a-z0-9_.]+) \[", user, re.M))

        def has(k):
            return k in keys

        def verb(k):   # the direction shown in the fact line, written in the model's own words
            m = re.search(r"^" + re.escape(k) + r" \[[^\]]*\b(reduction|increase|no change)\b", user, re.M)
            return {"reduction": "fall by", "increase": "rise by"}.get(m.group(1) if m else "", "change by")

        if schema is WhatIfParse:
            from backend.app.llm.advise import keyword_context
            q = user.split("<<<", 1)[-1].rsplit(">>>", 1)[0].strip()
            ctx = keyword_context(q)
            if ctx:   # like a real parse model: situation statements update the decision context
                parsed = WhatIfParse(kind="update_context", add=[], remove=[], unsupported=[],
                                     **{k: v for k, v in ctx.items() if k in WhatIfParse.model_fields})
            else:
                parsed = keyword_parse(q, json.loads(re.search(r"CURRENT_SELECTED_MEASURES: (\[.*?\])", user)
                                                     .group(1).replace("'", '"')))
        elif schema is WhatIfText:
            parts = [f"Compared with the previous plan, gas use would {verb('diff.gas_saving_kwh')} "
                     "{diff.gas_saving_kwh}." if has("diff.gas_saving_kwh") else ""]
            parsed = WhatIfText(whatif=" ".join(p for p in parts if p))
        else:
            parsed = ExplanationText(
                score=("Your home's Green Home Score is {green_home_score.before.total}, classed as "
                       "{green_home_score.before.class}.") if has("green_home_score.before.total") else "",
                issues="", plan="",
                energy=(f"Gas use is estimated to {verb('energy_results.change.gas_saving_kwh')} "
                        "{energy_results.change.gas_saving_kwh}. This saves about 12,345 kWh in total.")
                if has("energy_results.change.gas_saving_kwh") else "",
                carbon="", cost="", value="", not_suitable="",
                caveats="All of these figures are estimates, not guarantees.")
        return client_mod.LLMResult(parsed, "mock-model", False, 1, {"input_tokens": 0, "output_tokens": 0},
                                    provider="mock")


def _get(d: dict, dotted: str):
    for p in dotted.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def _engine_numbers(home_id: str, measures, new_request: dict | None) -> list[float]:
    """Engine values for an independent factual check: fresh builds, plus what-if differences."""
    base = build(ScenarioRequest(home_id=home_id, measures=measures)).model_dump(mode="json")
    vals = list(build_payload(base)["values"].values())
    if new_request:
        new = build(ScenarioRequest.model_validate(new_request)).model_dump(mode="json")
        pn, pb = build_payload(new)["values"], build_payload(base)["values"]
        vals += list(pn.values())
        vals += [round(pb[k] - pn[k], 1) for k in pn if k in pb] + [round(pn[k] - pb[k], 1) for k in pn if k in pb]
    return vals


def _factual(cited: list[dict], engine: list[float]) -> tuple[int, int, list[str]]:
    ok, bad = 0, []
    for c in cited:
        v = c.get("value")
        if not isinstance(v, (int, float)):
            continue
        match = any(abs(float(v) - e) <= 1e-6 * max(1.0, abs(e)) or abs(round(float(v), 1) - round(e, 1)) < 1e-9
                    for e in engine)
        shown = [_parse(t) for t in re.findall(r"\d[\d,]*(?:\.\d+)?", c.get("display", ""))]
        consistent = not shown or any(round(x, 6) in _forms(float(v)) for x in shown if x is not None)
        if match and consistent:
            ok += 1
        else:
            bad.append(f"{c['key']}={v} ({c.get('display')})")
    return ok, ok + len(bad), bad


def run_item(api, item: dict, use_llm: bool) -> dict[str, Any]:
    e, q = item["expect"], item["question"]
    body = {"home_id": item["home_id"], "question": q, "use_llm": use_llm}
    if item["expect"].get("measures") or item.get("measures"):
        body["measures"] = item["expect"].get("measures") or item.get("measures")
    route = e["route"]
    t0 = time.perf_counter()
    path = "/whatif" if route in ("whatif", "advice") else "/explain"
    resp = api.post(path, json=body)
    ms = int(1000 * (time.perf_counter() - t0))
    if resp.status_code != 200:
        return {"id": item["id"], "category": item["category"], "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    r = resp.json()
    kind = r.get("kind")
    refused = kind == "out_of_scope" or r.get("outcome") == "invalid_request"
    checks: dict[str, bool] = {"route": kind == route, "refusal": refused == e.get("refused", False)}
    text = r.get("answer", "")
    for rx in e.get("contains", []):
        checks[f"contains:{rx}"] = bool(re.search(rx, text, re.I))
    for rx in e.get("not_contains", []):
        checks[f"not_contains:{rx}"] = not re.search(rx, text, re.I)
    whatif_ok = None
    if route in ("whatif", "advice"):
        w = {}
        if "outcome" in e:
            w["outcome"] = r.get("outcome") == e["outcome"]
        if "recalculated" in e:
            w["recalculated"] = bool(r.get("recalculated")) == e["recalculated"]
        for f in ("added", "removed", "blocked"):
            if f in e:
                w[f] = sorted(r.get(f) or []) == sorted(e[f])
        for path_, want in (e.get("request") or {}).items():
            w[f"request:{path_}"] = _get(r.get("new_request") or {}, path_) == want
        if e.get("recalculated") and route == "whatif":
            w["new_scenario_id"] = r.get("scenario_id") != r.get("previous_scenario_id")
        whatif_ok = all(w.values())
        checks.update({f"whatif:{k}": v for k, v in w.items()})
    nums = r.get("numbers") or {}
    sentences = [s for s in _SENT.split(text) if s.strip() and not s.strip().endswith(":") and len(s.split()) > 2]
    unmatched = nums.get("unmatched") or []
    unsupported_sents = sum(1 for s in sentences if any(t in s for t in unmatched))
    engine = _engine_numbers(item["home_id"], body.get("measures"), r.get("new_request")) if r.get("cited_values") else []
    f_ok, f_n, f_bad = _factual(r.get("cited_values") or [], engine)
    return {"id": item["id"], "category": item["category"], "home": item["home"], "question": q, "kind": kind,
            "outcome": r.get("outcome"), "source": r.get("source"), "fallback_reason": r.get("fallback_reason"),
            "provider": r.get("provider"), "model": r.get("model"), "refused": refused,
            "numbers_total": nums.get("total", 0), "numbers_matched": nums.get("matched", 0), "unmatched": unmatched,
            "sentences": len(sentences), "unsupported_sentences": unsupported_sents,
            "cited_total": f_n, "cited_correct": f_ok, "cited_wrong": f_bad,
            "whatif_ok": whatif_ok, "checks": checks, "passed": all(checks.values()),
            "llm_stats": r.get("llm_stats"), "latency_ms": ms, "answer": text}


def summarise(rows: list[dict]) -> dict:
    ok_rows = [r for r in rows if "error" not in r]
    n_num = sum(r["numbers_total"] for r in ok_rows)
    n_match = sum(r["numbers_matched"] for r in ok_rows)
    n_cited = sum(r["cited_total"] for r in ok_rows)
    n_correct = sum(r["cited_correct"] for r in ok_rows)
    n_sent = sum(r["sentences"] for r in ok_rows)
    n_unsup = sum(r["unsupported_sentences"] for r in ok_rows)
    wi = [r["whatif_ok"] for r in ok_rows if r["whatif_ok"] is not None]
    llm_sent = sum((r.get("llm_stats") or {}).get("llm_sentences", 0) for r in ok_rows)
    dropped = sum((r.get("llm_stats") or {}).get("dropped", 0) for r in ok_rows)
    s = {
        "n_items": len(rows), "n_errors": len(rows) - len(ok_rows),
        "groundedness": round(n_match / n_num, 4) if n_num else 1.0, "numbers_total": n_num,
        "answers_fully_grounded": round(sum(r["numbers_matched"] == r["numbers_total"] for r in ok_rows) / max(1, len(ok_rows)), 4),
        "factual_accuracy": round(n_correct / n_cited, 4) if n_cited else 1.0, "cited_total": n_cited,
        "unsupported_claim_rate": round(n_unsup / n_sent, 4) if n_sent else 0.0, "sentences_total": n_sent,
        "whatif_success": round(sum(wi) / len(wi), 4) if wi else None, "n_whatif": len(wi),
        "refusal_correctness": round(sum(r["checks"]["refusal"] for r in ok_rows) / max(1, len(ok_rows)), 4),
        "route_correctness": round(sum(r["checks"]["route"] for r in ok_rows) / max(1, len(ok_rows)), 4),
        "items_all_checks_passed": round(sum(r["passed"] for r in ok_rows) / max(1, len(ok_rows)), 4),
        "sources": {k: sum(r.get("source") == k for r in ok_rows) for k in ("llm", "llm_patched", "template")},
        "llm_sentences": llm_sent, "llm_sentences_rejected_by_checker": dropped,
        "llm_sentence_acceptance": round(1 - dropped / llm_sent, 4) if llm_sent else None,
        "latency_ms_median": sorted(r["latency_ms"] for r in ok_rows)[len(ok_rows) // 2] if ok_rows else None,
    }
    s["targets_met"] = {"groundedness": s["groundedness"] >= TARGETS["groundedness"],
                        "factual_accuracy": s["factual_accuracy"] >= TARGETS["factual_accuracy"],
                        "unsupported_claim_rate": s["unsupported_claim_rate"] < TARGETS["unsupported_claim_rate"]}
    by_cat: dict[str, dict] = {}
    for r in ok_rows:
        c = by_cat.setdefault(r["category"], {"n": 0, "passed": 0})
        c["n"] += 1
        c["passed"] += int(r["passed"])
    s["by_category"] = by_cat
    s["failed_items"] = [{"id": r["id"], "category": r["category"], "failed": [k for k, v in r["checks"].items() if not v]}
                         for r in ok_rows if not r["passed"]]
    return s


def main(mode: str) -> dict:
    from fastapi.testclient import TestClient
    from backend.app.main import app

    providers = [p for p in client_mod.status()["providers"] if p["key_set"]]
    if mode == "llm" and not providers:
        raise SystemExit("mode llm needs an LLM API key in the environment (ANTHROPIC_API_KEY, GROQ_API_KEY or "
                         "GEMINI_API_KEY); none is set. Run --mode template or --mode mock, or set a key.")
    mock = None
    if mode == "mock":
        mock = MockLLM()
        client_mod._DEFAULT_CLIENT = mock
    service.clear_cache()
    items = json.loads(EVAL_SET.read_text())["items"]
    api = TestClient(app)
    t0 = time.time()
    rows = []
    for k, it in enumerate(items, 1):
        rows.append(run_item(api, it, use_llm=mode != "template"))
        r = rows[-1]
        print(f"[{k}/{len(items)}] {it['id']} {it['category']}: {'ok' if r.get('passed') else 'FAIL'} "
              f"source={r.get('source')} {r.get('latency_ms')}ms [{time.time() - t0:.0f}s]", flush=True)
        if mode == "llm" and r.get("kind") == "explain" and r.get("source") == "template" \
                and "unavailable" in str(r.get("fallback_reason") or ""):
            # every provider is out of quota: stop rather than report template answers as an LLM run. Successful
            # LLM answers are cached, so a rerun after the quota frees resumes from here at no cost.
            raise SystemExit(f"stopped at {it['id']}: LLM quota exhausted ({str(r.get('fallback_reason'))[:160]}). "
                             "Rerun later; completed answers are cached.")
    summary = summarise(rows)
    out = {"mode": mode, "date": str(date.today()), "eval_set": str(EVAL_SET.relative_to(ROOT)),
           "providers": [{"provider": p["provider"], "models": p["models"]} for p in providers] if mode == "llm" else
           ([{"provider": "mock"}] if mock else []), "targets": TARGETS, "summary": summary,
           "runtime_s": round(time.time() - t0, 1), "rows": rows}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"llm_eval_{mode}.json"
    if mode == "llm" and summary["sources"]["template"] > summary["n_items"] / 2:
        name = "llm_eval_llm_partial.json"   # a mostly-template run is never reported as the LLM result
        print(f"most answers came from the template ({summary['sources']}): written to {name}, not reported")
    (OUT_DIR / name).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("by_category",)}, indent=1))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("llm", "template", "mock"), default=None)
    a = ap.parse_args()
    mode = a.mode or ("llm" if any(p["key_set"] for p in client_mod.status()["providers"]) else "template")
    main(mode)
    import write_llm_evaluation_md  # noqa: E402  (same folder)
    write_llm_evaluation_md.main()
