"""Precompute and cache the LLM answers the demo will show, so the live demo never waits on a server.

    venv/bin/python eval/warm_cache.py                       # demo homes + scripted what-ifs
    venv/bin/python eval/warm_cache.py --engine fake_engine:run --homes york-demo-poor-semi

Run it after any change to the prompt, the facts or the engine (those change the cache key), and check
that every line says source=llm or llm_patched. Answers land in backend/.cache/llm/ and are reused by
the API automatically, with any provider order, even offline.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests" / "llm"), str(ROOT / "eval")]

from backend.app.llm.explain import explain  # noqa: E402
from backend.app.llm.whatif import answer_whatif  # noqa: E402

DEMO_HOMES = ["syn-poor-semi", "syn-flat-mid", "syn-missing-walls"]  # swap for the York demo homes (configs/demo_homes.json)
DEMO_QUESTIONS = ["What if I add a heat pump?", "What if I don't do the solar panels?",
                  "Can I add solid wall insulation?", "How much will my bills go down in pounds?"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="synthetic_homes:run")
    ap.add_argument("--check", action="store_true", help="cache-only: fail if any demo answer would need a live call")
    ap.add_argument("--homes", nargs="*", default=DEMO_HOMES)
    ap.add_argument("--questions", nargs="*", default=DEMO_QUESTIONS)
    args = ap.parse_args()
    if args.check:
        os.environ["LLM_PROVIDERS"] = "none"  # answers must come from the caches
    os.environ.setdefault("LLM_MAX_WAIT_S", "90")
    os.environ.setdefault("LLM_CACHE_DIR", str(ROOT / "eval" / "llm_cache"))  # demo answers ship with the repo
    mod, fn = args.engine.split(":")
    runner = getattr(importlib.import_module(mod), fn)

    missing = 0
    for pid in args.homes:
        scenario = runner(pid, None)
        t = time.time()
        res = explain(scenario)
        missing += res.source == "template"
        print(f"{pid:<24} report        source={res.source:<12} provider={res.provider} {time.time() - t:5.1f}s")
        for q in args.questions:
            t = time.time()
            ans = answer_whatif(scenario, q, runner)
            # Declines and no-change answers are template text by design; recalculated ones should be LLM text.
            missing += ans.recalculated and ans.explanation.source == "template"
            print(f"{pid:<24} what-if       source={ans.explanation.source:<12} kind={ans.outcome.kind:<16} "
                  f"{time.time() - t:5.1f}s  {q}")
    if args.check:
        print("demo cache complete" if not missing else f"{missing} demo answer(s) not cached: run without --check")
        sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
