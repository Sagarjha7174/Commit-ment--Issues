"""Customer memory demo (brief section 10): show how the recommendation changes as memory builds up.

    venv/bin/python eval/memory_demo.py              # template text, no API calls
    venv/bin/python eval/memory_demo.py --llm        # LLM text (uses quota; cached)

Three sessions for one customer on one home, written to eval/results/memory_demo.md:
  1. no context      -> the engine's default plan
  2. "I'm a tenant and we're moving next year"
  3. "My landlord set a budget of £8,000. We already did the loft insulation, and we don't want a heat pump"
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "eval")]

import synthetic_homes as sh  # noqa: E402
from backend.app.llm import memory  # noqa: E402
from backend.app.llm.advise import advise, advise_whatif  # noqa: E402
from backend.app.llm.facts_view import canonical  # noqa: E402
from backend.app.llm.measures import display_name  # noqa: E402

SESSIONS = [None, "I'm a tenant and we're moving next year",
            "My landlord set a budget of £8,000. We already did the loft insulation, and we don't want a heat pump"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--home", default="syn-poor-semi")
    args = ap.parse_args()
    os.environ.setdefault("LLM_CACHE_DIR", str(ROOT / "eval" / "llm_cache"))
    memory.MEMORY_DIR = Path(tempfile.mkdtemp(prefix="gh-memory-"))  # a fresh customer every run
    lines = ["# Customer memory demo", "", f"Home: `{args.home}` (synthetic test home, real engine). "
             "Each session reuses what the customer told us before.", ""]
    for i, q in enumerate(SESSIONS, 1):
        res = advise(args.home, sh.run, customer_id="demo", use_llm=args.llm) if q is None else \
            advise_whatif(args.home, q, sh.run, customer_id="demo", use_llm=args.llm)
        plan = [display_name(m) for m in canonical(res.scenario).get("selected_measures") or []]
        lines += [f"## Session {i}: {q or '(no context yet)'}", "",
                  f"- Plan: {', '.join(plan) or 'no measures'}",
                  f"- Explanation source: {res.explanation.source}", ""]
        for s in res.explanation.rendered.sections:
            if s.id in ("fit", "plan", "next_steps"):
                lines += [f"**{s.title}**", " ".join(c.text for c in s.claims), ""]
        print(f"session {i}: plan={plan} source={res.explanation.source}")
    out = ROOT / "eval" / "results" / "memory_demo.md"
    out.write_text("\n".join(lines))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
