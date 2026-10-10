"""What-if parsing accuracy: the LLM parser vs the keyword baseline, on hand-labelled questions.

    venv/bin/python eval/run_parse_eval.py              # keyword baseline only (free)
    venv/bin/python eval/run_parse_eval.py --llm        # plus the LLM parse model (uses quota; cached)

Labels (eval/whatif_questions.jsonl) give, for a current plan, the question's kind and the plan the user is
asking for. A parse is scored on the plan it produces ((current + add) - remove) and on its kind, plus
per-change precision/recall over (add|remove, measure) pairs. Code still validates feasibility afterwards,
so this measures understanding only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "eval")]

from backend.app.llm.client import LLMClient, LLMSettings  # noqa: E402
from backend.app.llm.whatif import keyword_parse, parse_question  # noqa: E402
from run_llm_eval import wilson  # noqa: E402


def plan_from(parse, current: list[str]) -> list[str]:
    add, remove = set(parse.add) - set(parse.remove), set(parse.remove) - set(parse.add)
    return sorted((set(current) | add) - remove)


def changes(current: list[str], plan: list[str]) -> set[tuple[str, str]]:
    return {("add", m) for m in set(plan) - set(current)} | {("remove", m) for m in set(current) - set(plan)}


def score(rows: list[dict], name: str) -> dict:
    n = len(rows)
    plan_ok = sum(r["plan"] == r["expected_plan"] for r in rows)
    kind_ok = sum(r["kind"] == r["expected_kind"] for r in rows)
    both = sum(r["plan"] == r["expected_plan"] and r["kind"] == r["expected_kind"] for r in rows)
    tp = fp = fn = 0
    for r in rows:
        exp, got = changes(r["current"], r["expected_plan"]), changes(r["current"], r["plan"])
        tp, fp, fn = tp + len(exp & got), fp + len(got - exp), fn + len(exp - got)
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    return {"parser": name, "questions": n,
            "plan_accuracy": round(plan_ok / n, 3), "plan_accuracy_ci95": wilson(plan_ok, n),
            "kind_accuracy": round(kind_ok / n, 3), "kind_accuracy_ci95": wilson(kind_ok, n),
            "exact_match": round(both / n, 3), "exact_match_ci95": wilson(both, n),
            "change_precision": round(prec, 3), "change_recall": round(rec, 3),
            "change_f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
            "errors": [{"id": r["id"], "question": r["question"], "expected": [r["expected_kind"], r["expected_plan"]],
                        "got": [r["kind"], r["plan"]]} for r in rows
                       if r["plan"] != r["expected_plan"] or r["kind"] != r["expected_kind"]]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--providers", default=None)
    args = ap.parse_args()
    os.environ.setdefault("LLM_CACHE_DIR", str(ROOT / "eval" / "llm_cache"))
    os.environ.setdefault("LLM_MAX_WAIT_S", "90")
    if args.providers:
        os.environ["LLM_PROVIDERS"] = args.providers
    labelled = [json.loads(line) for line in (ROOT / "eval" / "whatif_questions.jsonl").read_text().splitlines()]

    results = []
    runs = [("keyword", None)] + ([("llm", LLMClient(LLMSettings(enabled=True)))] if args.llm else [])
    for name, client in runs:
        rows = []
        for q in labelled:
            if client is None:
                parsed, source = keyword_parse(q["question"], q["current"]), "keywords"
            else:
                parsed, source = parse_question(q["question"], q["current"], use_llm=True, client=client)
            rows.append({**q, "expected_kind": q["kind"], "kind": parsed.kind, "plan": plan_from(parsed, q["current"]),
                         "source": source})
        res = score(rows, name)
        if client is not None:
            res["fell_back_to_keywords"] = sum(r["source"] == "keywords" for r in rows)
        results.append(res)
        print(f"{name:<8} plan {res['plan_accuracy']:.0%} {res['plan_accuracy_ci95']}  kind {res['kind_accuracy']:.0%}  "
              f"exact {res['exact_match']:.0%}  change F1 {res['change_f1']:.2f}  errors {len(res['errors'])}")
    out = ROOT / "eval" / "results" / "parse_eval.json"
    out.write_text(json.dumps({"labelled_questions": "eval/whatif_questions.jsonl", "results": results}, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
