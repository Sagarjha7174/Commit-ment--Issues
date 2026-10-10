"""Run the LLM test suite and write eval/results/llm.json (+ per-case rows and a human-review sheet).

    venv/bin/python eval/make_scenarios.py                              # (re)build eval/scenarios.jsonl
    venv/bin/python eval/run_llm_eval.py --template-only                # free: the deterministic baseline
    venv/bin/python eval/run_llm_eval.py --split dev                    # LLM on dev scenarios (prompt tuning)
    venv/bin/python eval/run_llm_eval.py --split heldout --judge 40     # final numbers for the report

Deterministic checks run on every case (by scenario type, see EXPECT below). The
LLM judge (a different model from the generator) is supplementary and runs on a
sample. Results are reported by scenario type, never as one blended number.
Repeated runs hit the LLM output cache, so they are reproducible and free.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import random
import statistics
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests" / "llm"), str(ROOT / "eval")]

from backend.app.llm.advise import advise  # noqa: E402
from backend.app.llm.checker import (ELEC_KEY, NOT_ASSESSED_RE, PERMISSION_CLAIM_RE, PRIVACY_RE,  # noqa: E402
                                     _not_negated, banned_phrases, claim_keys)
from backend.app.llm.context import NOT_ASSESSED, UserContext  # noqa: E402
from backend.app.llm.client import LLMClient, LLMSettings, LLMUnavailable  # noqa: E402
from backend.app.llm.explain import EXPLAIN_PROMPT_VERSION, StaleScenarioError, explain, load_prompt  # noqa: E402
from backend.app.llm.facts_view import build_factsheet, canonical  # noqa: E402
from backend.app.llm.measures import mentioned_measures  # noqa: E402
from backend.app.llm.whatif import answer_whatif  # noqa: E402

RESULTS = ROOT / "eval" / "results"
# Approximate $/MTok (input, output, cache read, cache write) for the cost estimate.
PRICES = {"claude-opus-5-5": (4.0, 20.0, 0.20, 5.0), "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.5),
          "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125)}


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """95% Wilson score interval for k successes out of n (honest on small samples and rates near 0 or 1)."""
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def load_runner(spec: str):
    mod, fn = spec.split(":")
    return getattr(importlib.import_module(mod), fn)


# --- Deterministic expectations -------------------------------------------------------------------------------

def evaluate(case: dict, text: str, draft, outcome, scenario: dict, expl_scenario_id: str) -> dict[str, bool]:
    exp = case["expect"]
    scenario = canonical(scenario)  # engine results and the contract read the same way
    checks: dict[str, bool] = {
        "rendered_complete": "{" not in text and "None" not in text,
        "scenario_id_matches": expl_scenario_id == scenario.get("scenario_id"),
        "no_banned_phrases": not banned_phrases(text),
    }
    if exp.get("mentions_warnings"):
        checks["warnings_passed_on"] = all(w in text for w in scenario.get("warnings") or [])
    if exp.get("mentions_missing"):
        checks["missing_data_acknowledged"] = any(w in text.lower() for w in ("missing", "not estimated",
                                                                              "not available", "unknown"))
    if exp.get("blocked"):
        for m in exp["blocked"]:
            checks[f"blocked_{m}"] = bool(outcome and m in outcome.blocked)
            checks[f"explained_{m}"] = any(c.type == "feasibility" and (m in c.measures or m in mentioned_measures(c.text))
                                           for c in draft.claims)
        checks["infeasible_not_applied"] = not (set(exp["blocked"]) & set(scenario.get("selected_measures") or []))
    if exp.get("electricity_rises"):
        # Compared with the plan before the question (a package with solar can still cut electricity overall).
        before = case.get("_prev_elec_after")
        after = ((scenario.get("energy_results") or {}).get("after") or {}).get("grid_elec_kwh")
        checks["engine_shows_rise"] = isinstance(before, (int, float)) and isinstance(after, (int, float)) and after > before
        # Any accepted sentence citing the electricity change has passed the checker's direction rule ("rises").
        checks["rise_stated"] = any({ELEC_KEY, "diff.grid_elec_saving_kwh"} & claim_keys(c) for c in draft.claims)
    if exp.get("says_not_estimated"):
        checks["says_not_estimated"] = "not estimated" in text.lower() or "not available" in text.lower()
    # Persona (decision-context) expectations
    if case["type"] == "persona":
        low = text.lower()
        claims_text = text.replace(NOT_ASSESSED, " ")  # our own "not assessed here: ... payback ..." disclaimer

        def asserts(rx) -> bool:  # a non-negated occurrence anywhere in the rendered explanation
            return any(_not_negated(claims_text, m.start()) for m in rx.finditer(claims_text))
        checks["no_permission_claims"] = not asserts(PERMISSION_CLAIM_RE)
        checks["no_bill_payback_or_climate_claims"] = not asserts(NOT_ASSESSED_RE)
        checks["no_comments_on_finances"] = not asserts(PRIVACY_RE)
        plan = set(scenario.get("selected_measures") or [])
        if exp.get("consent_language"):
            checks["consent_language"] = "landlord" in low and ("check" in low or "consent" in low)
        if exp.get("who_benefits"):
            checks["who_benefits_stated"] = "who pays and who benefits" in low or "benefit" in low
        if exp.get("budget_respected") is not None:
            cost = (scenario.get("cost_results") or {}).get("package_cost_gbp")
            checks["budget_respected"] = not plan or (cost is not None and cost <= exp["budget_respected"])
        if exp.get("excluded"):
            checks["excluded_not_in_plan"] = not (plan & set(exp["excluded"]))
    if exp.get("kind"):
        checks["kind_correct"] = bool(outcome and outcome.kind == exp["kind"])
        checks["not_recalculated"] = expl_scenario_id == case["_base_id"]
    return checks


# --- LLM judge (supplementary) --------------------------------------------------------------------------------

class Verdict(BaseModel):
    index: int
    verdict: Literal["supported", "unsupported", "contradicted"]
    note: str


class JudgeOutput(BaseModel):
    verdicts: list[Verdict]


JUDGE_PROMPT_VERSION = "judge_v2"


def judge(client: LLMClient, scenario: dict, sentences: list[str]) -> tuple[list[Verdict], str]:
    """Sentence-level verdicts from a model other than the generator. It sees every number, plus the facts code
    derived from the scenario (plan order, ranked score parts...), which the explanation may legitimately cite."""
    sheet = build_factsheet(scenario)
    derived = {k: f.value for k, f in sorted(sheet.facts.items()) if k.startswith(("derived.", "feasibility."))
               and f.available}
    user = ("SCENARIO:\n" + json.dumps(scenario, sort_keys=True) + "\n\nDERIVED FACTS:\n" +
            json.dumps(derived, sort_keys=True) + "\n\nSENTENCES:\n" +
            "\n".join(f"{i}. {s}" for i, s in enumerate(sentences)))
    res = client.structured(system=load_prompt(JUDGE_PROMPT_VERSION), user=user, schema=JudgeOutput,
                            max_tokens=6000, purpose="judge", role="judge")
    return res.parsed.verdicts, f"{res.provider}:{res.model}"


# --- Main -------------------------------------------------------------------------------------------------------

def run_case(case: dict, runner, use_llm: bool, client: LLMClient | None) -> dict[str, Any]:
    scenario = runner(case["property_id"], case["measures"])
    case["_base_id"] = scenario["scenario_id"]
    case["_prev_elec_after"] = ((canonical(scenario).get("energy_results") or {}).get("after") or {}).get("grid_elec_kwh")
    row: dict[str, Any] = {k: case[k] for k in ("id", "type", "split", "property_id", "mode", "question")}
    t0 = time.perf_counter()
    if case["type"] == "stale":
        stale = runner(case["property_id"], case["expect"].get("stale_from"))
        try:
            explain(scenario, use_llm=False, current_scenario_id=stale["scenario_id"])
            row["checks"] = {"stale_rejected": stale["scenario_id"] == scenario["scenario_id"]}
        except StaleScenarioError:
            row["checks"] = {"stale_rejected": True}
        row.update(source="n/a", passed=all(row["checks"].values()), latency_ms=0)
        return row

    outcome = None
    if case["mode"] == "advise":
        adv = advise(case["property_id"], runner, context=UserContext(**case["expect"].get("context", {})),
                     use_llm=use_llm, client=client)
        res, final = adv.explanation, adv.scenario
        case["_base_id"] = res.scenario_id
    elif case["mode"] == "report":
        res = explain(scenario, use_llm=use_llm, question=case.get("question"), client=client)
        final = scenario
    else:
        ans = answer_whatif(scenario, case["question"], runner, use_llm=use_llm, client=client)
        res, outcome, final = ans.explanation, ans.outcome, ans.scenario
    text = res.rendered.all_text
    checks = evaluate(case, text, res.draft, outcome, final, res.scenario_id)
    row.update(
        source=res.source, provider=res.provider, attempts=res.attempts, cached=res.cached,
        fallback_reason=res.fallback_reason, llm_sentences=res.llm_sentences, dropped=res.dropped,
        template_filled=res.template_filled, origins=res.origins,
        latency_ms=int((time.perf_counter() - t0) * 1000), llm_ms=res.llm_ms,
        usage=res.usage,
        checks=checks, passed=all(checks.values()), scenario_id=res.scenario_id,
        outcome=None if outcome is None else {"kind": outcome.kind, "added": outcome.added,
                                              "removed": outcome.removed, "blocked": outcome.blocked,
                                              "parser": outcome.parser},
        sentences=[c.text for s in res.rendered.sections for c in s.claims],
        _scenario=final,
    )
    return row


def summarise(rows: list[dict], model: str | None, judged: list[dict]) -> dict[str, Any]:
    by_type: dict[str, dict[str, Any]] = {}
    for r in rows:
        t = by_type.setdefault(r["type"], {"n": 0, "passed": 0, "failed_checks": {}})
        t["n"] += 1
        t["passed"] += r["passed"]
        for name, ok in r["checks"].items():
            if not ok:
                t["failed_checks"][name] = t["failed_checks"].get(name, 0) + 1
    for t in by_type.values():
        t["pass_rate"] = round(t["passed"] / t["n"], 3)
        t["pass_rate_ci95"] = wilson(t["passed"], t["n"])

    explained = [r for r in rows if r["source"] != "n/a"]
    sources = {s: sum(r["source"] == s for r in explained) for s in ("llm", "llm_patched", "template")}
    n = max(len(explained), 1)
    codes: dict[str, int] = {}
    for r in explained:
        for d in r.get("dropped") or []:
            for e in d["errors"]:
                code = e.split("[", 1)[-1].split("]", 1)[0]
                codes[code] = codes.get(code, 0) + 1
    llm_rows = [r for r in explained if r["source"] in ("llm", "llm_patched")]
    written = sum(r.get("llm_sentences") or 0 for r in llm_rows)
    rejected = sum(len(r.get("dropped") or []) for r in llm_rows)
    providers: dict[str, int] = {}
    for r in llm_rows:
        providers[r.get("provider") or "?"] = providers.get(r.get("provider") or "?", 0) + 1
    live = [r["llm_ms"] for r in explained if not r.get("cached") and r.get("llm_ms")]
    tok = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    for r in explained:
        for u in r.get("usage") or []:
            for k in tok:
                tok[k] += u.get(k) or 0
    p = PRICES.get(model)
    cost = None if not p else round((tok["input_tokens"] * p[0] + tok["output_tokens"] * p[1] +
                                     tok["cache_read_input_tokens"] * p[2] +
                                     tok["cache_creation_input_tokens"] * p[3]) / 1e6, 4)
    out: dict[str, Any] = {
        "by_type": by_type,
        "cases": len(rows),
        "all_checks_pass_rate": round(sum(r["passed"] for r in rows) / max(len(rows), 1), 3),
        "all_checks_pass_rate_ci95": wilson(sum(r["passed"] for r in rows), len(rows)),
        "explanation_sources": sources,
        "llm_used_rate": round(len(llm_rows) / n, 3),
        "clean_llm_rate": round(sources["llm"] / n, 3),
        "template_fallback_rate": round(sources["template"] / n, 3),
        "llm_sentence_acceptance": round(1 - rejected / written, 3) if written else None,
        "llm_sentence_acceptance_ci95": wilson(written - rejected, written),
        "llm_sentences": {"written": written, "rejected": rejected,
                          "template_filled": sum(r.get("template_filled") or 0 for r in llm_rows)},
        "multi_attempt_rate": round(sum((r.get("attempts") or 0) > 1 for r in explained) / n, 3),
        "providers_used": providers,
        "cases_answered_from_cache": sum(bool(r.get("cached")) for r in llm_rows),  # replays: no live tokens/latency
        "rejections_by_code": dict(sorted(codes.items(), key=lambda kv: -kv[1])),
        "numeric_groundedness": "100% by construction: the LLM never sees or writes numbers; every displayed "
                                "number is filled in by code from the scenario result (see LLM.md).",
        "llm_call_ms": ({"p50": int(statistics.median(live)),
                                   "p95": int(sorted(live)[max(0, int(0.95 * len(live)) - 1)]), "n": len(live)}
                                  if live else None),
        "tokens": tok,
        "cost_estimate_usd": cost,
    }
    if judged:
        verdicts = [v for j in judged for v in j["verdicts"]]
        total = max(len(verdicts), 1)
        n_sup = sum(v["verdict"] == "supported" for v in verdicts)
        n_con = sum(v["verdict"] == "contradicted" for v in verdicts)
        n_uns = sum(v["verdict"] == "unsupported" for v in verdicts)
        origin_of = {r["id"]: r.get("origins") or [] for r in rows}
        by_origin: dict[str, dict[str, int]] = {}
        for j in judged:
            for v in j["verdicts"]:
                o = origin_of.get(j["id"], [])
                origin = o[v["index"]] if 0 <= v["index"] < len(o) else "unknown"
                d = by_origin.setdefault(origin, {"sentences": 0, "flagged": 0})
                d["sentences"] += 1
                d["flagged"] += v["verdict"] != "supported"
        out["judge"] = {
            "cases": len(judged), "sentences": len(verdicts),
            "sentences_shown": sum(j.get("sentences", 0) for j in judged),
            "groundedness": round(n_sup / total, 3), "groundedness_ci95": wilson(n_sup, total),
            "factual_accuracy": round(1 - n_con / total, 3), "factual_accuracy_ci95": wilson(total - n_con, total),
            "unsupported_claim_rate": round(n_uns / total, 3), "unsupported_claim_rate_ci95": wilson(n_uns, total),
            # Every judged sentence already passed our checker: judge flags on LLM-origin sentences are what the
            # checker missed; flags on template sentences point at template wording.
            "flags_by_sentence_origin": by_origin,
            "targets": {"groundedness": ">= 0.90", "factual_accuracy": ">= 0.90", "unsupported_claim_rate": "< 0.05"},
            "note": "Supplementary: judged by a second model on a sample; see human review for agreement.",
        }
    return out


def write_human_review(rows: list[dict], n: int, path: Path) -> None:
    hard = ["injection", "conflicting", "heat_pump_rise", "infeasible_whatif", "missing_data", "insufficient_data"]
    picked = [r for t in hard for r in rows if r["type"] == t and r.get("sentences")][: n * 3]
    rng = random.Random(42)
    rng.shuffle(picked)
    lines = ["# Human review sheet (LLM explanations)", "",
             "For each sentence mark S (supported), U (unsupported) or C (contradicted) against the scenario JSON in "
             "eval/results/llm_cases.jsonl. Then compare with the judge's verdicts.", ""]
    for r in picked[:n]:
        lines += [f"## {r['id']} ({r['type']}, source: {r['source']})", f"Question: {r.get('question') or '-'}", ""]
        lines += [f"- [ ] {i}. {s}" for i, s in enumerate(r["sentences"])] + [""]
    path.write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default=str(ROOT / "eval" / "scenarios.jsonl"))
    ap.add_argument("--engine", default=None, help="module:function (home_id, measures) -> result; default: the "
                                                  "engine recorded in the scenarios file")
    ap.add_argument("--template-only", action="store_true", help="no API calls: evaluate the template baseline")
    ap.add_argument("--split", choices=["all", "dev", "heldout"], default="all")
    ap.add_argument("--types", nargs="*", help="only these scenario types")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--per-type", type=int, default=None, help="take the first N cases of every scenario type")
    ap.add_argument("--judge", type=int, default=0, help="judge this many explained cases (LLM, or template with "
                                                         "--template-only)")
    ap.add_argument("--judge-providers", default="gemini,groq", help="judge provider chain (must not be the generator "
                                                                     "model)")
    ap.add_argument("--human-review", type=int, default=20)
    ap.add_argument("--tag", default=None, help="suffix for the output files, e.g. 'template' or 'v2'")
    ap.add_argument("--providers", default=None, help="provider chain for this run, e.g. 'groq' or 'groq,gemini'")
    ap.add_argument("--max-wait", type=float, default=90, help="seconds to wait on a rate limit before skipping")
    args = ap.parse_args()

    cases = [json.loads(line) for line in Path(args.scenarios).read_text().splitlines() if line.strip()]
    args.engine = args.engine or cases[0].get("engine", "fake_engine:run")
    runner = load_runner(args.engine)
    if args.split != "all":
        cases = [c for c in cases if c["split"] == args.split]
    if args.types:
        cases = [c for c in cases if c["type"] in args.types]
    if args.per_type:
        seen: dict[str, int] = {}
        picked = []
        for c in cases:
            if seen.get(c["type"], 0) < args.per_type:
                picked.append(c)
                seen[c["type"]] = seen.get(c["type"], 0) + 1
        cases = picked
    if args.limit:
        cases = cases[: args.limit]

    use_llm = not args.template_only
    # Answers behind reported results are written to the committed cache, so they can be reproduced without keys.
    os.environ.setdefault("LLM_CACHE_DIR", str(ROOT / "eval" / "llm_cache"))
    if args.providers:
        os.environ["LLM_PROVIDERS"] = args.providers
    os.environ["LLM_MAX_WAIT_S"] = str(args.max_wait)  # batch runs can afford to wait for rate limits
    settings = LLMSettings()
    client = LLMClient(settings) if use_llm else None
    rows = []
    for i, case in enumerate(cases, 1):
        row = run_case(case, runner, use_llm, client)
        rows.append(row)
        flag = "ok " if row["passed"] else "FAIL"
        print(f"[{i:3d}/{len(cases)}] {flag} {row['id']:<24} source={row['source']:<9} "
              f"{'' if row['passed'] else [k for k, v in row['checks'].items() if not v]}")

    judged = []
    if args.judge:
        jclient = LLMClient(LLMSettings(providers=tuple(args.judge_providers.split(",")), enabled=True))
        sources = ("template",) if args.template_only else ("llm", "llm_patched")
        pool = [r for r in rows if r["source"] in sources and r.get("sentences")]
        random.Random(42).shuffle(pool)
        for r in pool[: args.judge]:
            try:
                v, judge_model = judge(jclient, r["_scenario"], r["sentences"])
                judged.append({"id": r["id"], "type": r["type"], "judge": judge_model,
                               "sentences": len(r["sentences"]), "verdicts": [x.model_dump() for x in v]})
                print(f"judged {r['id']} with {judge_model}")
            except LLMUnavailable as e:
                print(f"judge failed on {r['id']}: {e}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    tag = args.tag or ("template" if args.template_only else EXPLAIN_PROMPT_VERSION)
    summary = {
        "meta": {"date": date.today().isoformat(),
                 "providers": None if args.template_only else list(settings.providers),
                 "generator_models": None if args.template_only else
                 {p: settings.model_for(p, "explain") for p in settings.providers},
                 "judge_models": sorted({j["judge"] for j in judged}) or None,
                 "judge_prompt": JUDGE_PROMPT_VERSION if judged else None,
                 "prompt_version": EXPLAIN_PROMPT_VERSION,
                 "mode": "template-only" if args.template_only else "llm", "split": args.split,
                 "engine": args.engine, "scenarios_file": str(Path(args.scenarios).relative_to(ROOT))},
        **summarise(rows, None if args.template_only else settings.model_for(settings.provider, "explain"), judged),
    }
    name = "llm" if tag == EXPLAIN_PROMPT_VERSION and args.split in ("all", "heldout") else f"llm_{tag}_{args.split}"
    (RESULTS / f"{name}.json").write_text(json.dumps(summary, indent=2))
    with (RESULTS / f"{name}_cases.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps({k: v for k, v in r.items() if k != "_scenario"}) + "\n")
    if judged:
        (RESULTS / f"{name}_judge.json").write_text(json.dumps(judged, indent=2))
    write_human_review(rows, args.human_review, RESULTS / f"{name}_human_review.md")
    print(json.dumps({k: summary[k] for k in ("all_checks_pass_rate", "explanation_sources", "llm_used_rate",
                                               "llm_sentence_acceptance", "llm_sentences", "providers_used",
                                               "rejections_by_code", "llm_call_ms", "tokens")}, indent=1))
    print("by type:", {t: v["pass_rate"] for t, v in summary["by_type"].items()})
    print(f"wrote {RESULTS / (name + '.json')}")


if __name__ == "__main__":
    main()
