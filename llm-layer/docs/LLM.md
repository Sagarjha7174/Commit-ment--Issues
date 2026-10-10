# LLM layer (deliverable E)

Owner: P4. Code: `backend/app/llm/`. Tests: `tests/llm/`. Evaluation: `eval/make_scenarios.py`, `eval/run_llm_eval.py`, `eval/warm_cache.py`, results in `eval/results/`.

## What the LLM does, and what it never does

The LLM has three jobs:
1. Explain a scenario result to a homeowner.
2. Turn a free-text what-if question into a structured change to the measure set.
3. Explain the difference between two scenario results.

It never computes or estimates a number, chooses packages, decides feasibility, or judges data sources.

**It cannot write a number, and it never sees one.** The facts it receives are keys, meanings, units, statuses (available / unavailable / not estimated / needs verification), provenance labels and directions ("reduction", "increase"). Numeric values are withheld, and every figure inside text facts (warnings, assumptions, engine key issues) is masked with "#" before the LLM sees it, so it cannot copy one either. A test asserts that no fact value shown to the LLM contains a digit. It writes placeholders such as `{energy_results.change.gas_saving_kwh}`, and code fills them from the scenario result with one formatter (`render.py`). Every number shown therefore has the engine's value, unit and rounding: numeric groundedness by construction.

## Engine integration (`engine_map.py`, `engine.py`)

The layer runs on the team's engine (`backend/app/services/scenario_builder`, schema `backend/app/schemas/scenario.py`).
- **`engine_map.to_contract`** maps the engine's `ScenarioResult` onto the fact keys the prompt, checker and templates use:
  - `simulation`, `carbon`, `score_before` / `score_after` (with the engine's `key_issues`);
  - the feasibility list with `reason_text`;
  - `measures_applied` / `measures_blocked`, `valuation`, and package cost (from the package matching the applied measures);
  - status words: ok → available, not_estimated, unavailable / blocked → unavailable.
- **Plain English.** Engine warnings and reasons are rewritten for homeowners: per-measure "not validated against NEED" notes become one sentence, and internal references such as `docs/…` or "D14" are removed.
- **One adapter, one ID.** `facts_view.build_factsheet` accepts an engine result directly. The engine's own `scenario_id` is used.
- **Running the engine:** `engine.run_scenario(home_id, measures)`.
  - It uses the York data when it is present.
  - Otherwise `eval/synthetic_homes.py` supplies 10 **synthetic** test homes (poor semi, mid-floor flat, missing walls, no baseline, no electricity baseline, two conflicting EPC-vs-use homes, electric storage heating, an already-good home, unknown heating).
  - Tests, the evaluation and the dev server run the real engine on these homes; the fake engine remains only for fast unit tests.

## Decision context, permissions and memory (`context.py`, `advise.py`, `memory.py`)

This integrates the team's product concept (tenant, owner, landlord and seller modes; horizon; budget; permission statuses; split incentives; the decision record; "what changed and why"). It also implements the brief's optional **Customer Memory** extension. The LLM never decides any of it: deterministic code does, and the LLM explains the code-written facts under the usual checks.

- **`UserContext`** (every field optional; privacy-first, with bands and choices only):
  - role: tenant / owner-occupier / landlord / selling;
  - horizon: under two years … over ten;
  - priorities;
  - budget upper bound;
  - constraints: no roof access, listed or conservation, cannot alter the exterior, shared building;
  - measures already done or refused.

  Nothing is inferred about the person: no salary, job or credit, and the checker rejects comments on their finances.
- **Permission overlay** (the concept's statuses, on top of the engine's physical feasibility):
  - `not_feasible` (engine);
  - `unverified` (engine needs verification, or no roof access);
  - `conditional`, with who must agree:
    - a tenant → the landlord for every measure;
    - a flat or shared building → the building owner or managing agent for roof and outside-wall work;
    - listed or conservation → the planning authority for exterior work;
    - pre-1919 solid walls → a surveyor's damp and moisture check;
  - `ruled_out_by_you`;
  - `no_known_permission_needed`.

  We never say "confirmed": law is not verified here.
- **Plan choice** from the engine's own package search (no new optimiser):
  - refused, done, infeasible and ruled-out packages are dropped;
  - with a budget, the largest carbon saving within it;
  - a short horizon, a seller, a low-upfront-cost priority or a tenant → the lowest cost meeting the engine's 10% threshold;
  - a carbon priority → the largest saving;
  - otherwise the most carbon per pound (labelled literally).

  The engine is then rerun for that plan, so every number is the engine's.
- **New sections:**
  - "For you": situation, why this plan, who pays and who benefits, budget fit, left out at your request, since last time with the code-computed changes in emissions and cost.
  - "Before you start": who to ask and what to check.
  - Caveats also state what is **not assessed**: bills, payback, climate, occupancy, and whether permission will be granted.
- **Checker rules:**
  - `PERMISSION`: no "allowed / approved / can just install"; a tenant's recommendations must carry the consent;
  - `NOT_ASSESSED`: no payback, "pays for itself", bill or climate claims;
  - `BUDGET`: "within your budget" only when the code says so;
  - `PRIVACY`.

  `derived.plan_order` carries "(check first with your landlord)", so the plan sentence is correct by construction.
- **Memory and decision record:** one local JSON file per customer (`backend/.cache/memory/`, never committed, opaque IDs). Each recommendation is stored with its context, plan, choice rule, scenario ID, outcomes and versions. `what_changed()` explains what changed since last time and why.
- **Context from conversation.** A question can update the context ("I'm a tenant and we're moving next year", "my budget is £8,000", "we already did the loft", "we don't want a heat pump"):
  - the parser (`whatif_v2`, or the clause-scoped keyword fallback) returns `kind=update_context`;
  - code validates and merges it;
  - the plan is re-decided and explained.
- **API:**
  - `customer_id` / `context` on `/llm/explain` and `/llm/whatif`;
  - `GET`/`PUT /llm/profile/{id}`;
  - `GET /llm/history/{id}`.
- **Demo:** `eval/memory_demo.py` (results in `eval/results/memory_demo.md`) runs three sessions on one home:
  - no context → all six measures;
  - "I'm a tenant and we're moving next year" → cavity wall only, with landlord consent;
  - "My landlord set a budget of £8,000. We already did the loft insulation, and we don't want a heat pump" → cavity wall, double glazing and a smart thermostat within budget, explaining what changed.
- **Out of scope**, by the concept's own advice to stay narrow and verifiable in the UK: climate and hazards, tariffs, bills and payback, occupancy and appliance scenarios, contractor quotes, portfolios, non-UK rules.

## Algorithm (`explain.py`)

```
scenario ─► facts_view (catalogue, no numbers) ─► LLM: prose per section, placeholders only
                                                        │
          extract.py: one claim per sentence; code infers its type (saving / increase / missing data /
          feasibility / recommendation / caveat / statement) and its measures, from values and wording
                                                        │
          checker.check_claim on every sentence ─► failing sentences dropped (reasons logged)
                                                        │
          checker.coverage_gaps ─► each missing required piece filled with the matching template sentence
                                                        │
          full check ─► render (fills numbers) ─► post-render check (scenario ID current) ─► API / UI
```

- **One call in the normal case.** The LLM is asked again only if its answer is unusable: no sentences, or more than 40% rejected. In that case the rejected sentences and the reasons go back as feedback. If every provider fails, or fewer than 3 sentences survive, the deterministic template is used.
- **Why prose, not claim JSON.** The LLM writes a short paragraph per section; code splits it into sentences and decides what each one is. This is more reliable than asking the model to label its own sentences: in our first real runs, mislabelled claims were the main cause of rejections. It also gives the model freedom of wording and halves the output tokens.
- **Sources** are reported per explanation:
  - `llm`: every sentence accepted;
  - `llm_patched`: some dropped and/or template sentences added;
  - `template`.

  Each also records `llm_sentences`, `dropped` (with reasons) and `template_filled`, which the UI and the evaluation can show.

## Checks (`checker.py`)

**Per sentence:**
- **Numbers:** no digits, number words, `%` or `£` outside placeholders; no unit typed after a placeholder.
- **Keys:** every key exists. An unavailable value may only appear in a sentence that says it is not available.
- **Contradiction:** saying "not estimated" about a section whose figures all exist is rejected. This came from a real model output: "the value is not estimated because the valuation is exploratory".
- **Direction:** changes are rendered as sizes, so the wording must carry the direction. Each direction word ("falls", "rises", "saves", "increases"...) belongs to the nearest change placeholder in its clause, and it must match that value's sign:
  - "gas falls by X while electricity rises by Y" passes;
  - calling a rise a saving fails;
  - a zero change may not be called a rise or a fall.
- **Comparatives and superlatives:** only allowed when citing a code-ranked fact (`derived.score_drags`, `derived.largest_gas_saving_measure`).
- **Feasibility:**
  - infeasible measures are never recommended or credited with savings;
  - recommendations come only from the selected plan;
  - needs-verification measures must be described as needing a check. `derived.plan_order` already marks them "(needs checking on site first)", and text facts a sentence cites count as its wording;
  - a needs-verification measure may not be called unsuitable (`NEEDS_CHECK`). The LLM judge found this miss in a passing explanation;
  - feasible measures may not be called unsuitable.
- **Direction filters:** `{key|change}` renders "fall by X" / "rise by X" / "not change", and `{key|changes}` renders "falls by X" / "rises by X" / "does not change", so code writes the direction. Wording next to the placeholder that contradicts it is still rejected.
- **Interaction wording:** "the savings are not simply added" is rejected, because the per-measure savings come from a sequential simulation and do add up; interaction talk with only one measure is rejected too.
- **Banned phrases** (negation-aware): guarantees, "definitely", proven/causal claims, value promises, finance/mortgage/loan/investment advice, brands and suppliers, "digital twin".
- **Provenance wording:** "actual/measured usage" or "meter reading" is rejected unless the baseline is observed or user-provided.

**Coverage**, returned as structured gaps so each can be filled from the template:
- score and class;
- every selected measure (also when named through `{derived.plan_order}`);
- gas **and** grid electricity;
- carbon;
- value (indicative range, or why it is not estimated);
- every infeasible or needs-verification measure with its reason;
- every warning;
- missing details;
- "estimate" wording in the energy and carbon sections;
- in what-if mode: the gas and electricity change versus the previous plan.

**Post-render:**
- the scenario ID equals the one the app shows (otherwise `StaleScenarioError`, which the API returns as 409);
- no unfilled placeholder;
- no raw `None`;
- no duplicated unit.

**Template invariant:** `templates.py` produces a complete explanation for any scenario, and the tests assert it passes the checker **for every feasible measure combination of every demo home**.

## Providers, models and limits (`client.py`)

| Item | Value |
|---|---|
| Provider chain | `LLM_PROVIDERS=groq,gemini` (tried in order; the template is the last resort). Unset: every provider with a key in `.env` (`anthropic`, `groq`, `gemini`, `openrouter`, `deepseek`). Any failure moves to the next provider: rate limit, Groq 413, 5xx, network, safety block, invalid output or unknown model |
| Models per role | Groq: explain `openai/gpt-oss-120b`, parse and judge `openai/gpt-oss-20b` (`qwen/qwen3.8-27b` allows only 1,000 output tokens/min, too little to judge). Gemini: explain `gemini-3.5-flash`, parse `gemini-3.1-flash-lite`, judge `gemini-3.8-flash`. Anthropic: `claude-opus-5-5` (judge `claude-sonnet-5-5`). Overrides: `LLM_MODEL`, `LLM_PARSE_MODEL`, `LLM_JUDGE_MODEL`, or `LLM_<ROLE>_MODEL_<PROVIDER>`. The judge is always a different model from the generator |
| Reasoning | Turned down for this task: Groq gpt-oss `reasoning_effort=low`, Gemini 3 `thinking_level=LOW`, Anthropic effort `medium`/`low`. This cut output tokens per explanation on Groq from about 3,000 to about 900 |
| Output format | JSON-schema-constrained: Gemini `response_json_schema` (with `$ref`s inlined), OpenAI-style `response_format` (falling back to JSON mode), Anthropic `messages.parse` |
| Sampling | `temperature=0` where supported |
| Rate limits | A shared per-(provider, model) limiter on requests and tokens per minute. Defaults: Groq 30 requests and 8,000 tokens per minute; Gemini 10 requests per minute; override with `LLM_RPM_<P>` / `LLM_TPM_<P>`. If the wait would exceed `LLM_MAX_WAIT_S` (default 20 s; the evaluation uses 90 s), the next provider is tried |
| Output cache | Keyed by SHA-256 of (provider, model, role, prompt, input, schema); any cached answer is used before any live call (`LLM_CACHE=0` disables it). Ad-hoc development answers go to `backend/.cache/llm/` (not committed). **Answers behind reported results and the demo go to `eval/llm_cache/`, which is committed**, and every client reads it, so organisers can reproduce our reported explanations and judge verdicts, and run the demo, without API keys. `eval/run_llm_eval.py` and `eval/warm_cache.py` write there |
| Free-tier limits seen | Gemini `gemini-3.5-flash`: about 20 requests per day on our key. Groq `gpt-oss-120b`: 8,000 tokens per minute, plus a daily token cap |
| Template mode | `LLM_ENABLED=0`, or `template_mode: true` per request; no key needed |
| Call log | `backend/.cache/llm_calls.jsonl`: provider, model, latency, tokens, outcome |
| Data use | Free-tier prompts may be used by the provider to improve its products. We send only synthetic or open-government data, with no personal information (noted in RESPONSIBLE_AI.md) |

Keys (`GROQ_API_KEY`, `GEMINI_API_KEY`, optionally `ANTHROPIC_API_KEY`) go in the repo-root `.env`, which is never committed. `venv/bin/python -m app.llm.client` (run from `backend/`) prints the chain, models and limits. `--list-models --provider groq` lists what a key can use.

## Prompt size

The LLM sees one compact line per fact. Score-part detail, versions, raw lists and the details of feasible measures are hidden from it (they stay valid keys). What-if prompts carry only the differences and the new totals. A report request is about 2.7k input tokens (system prompt plus facts).

## What-if flow (`whatif.py`)

1. **Parse.** The small parse model returns `{kind, add, remove, unsupported}`. The measure lists are a closed enum, so it cannot invent a measure. If every provider is down, a conservative keyword parser takes over; it only acts on a measure when an action word comes before it in the same clause.
2. **Validate (code).**
   - Infeasible requests are blocked and never applied.
   - Needs-verification requests are applied but flagged.
   - Missing feasibility information is treated as needs-verification, never as infeasible.
3. **Rerun.** The engine reruns for the new measure set, which must contain exactly the validated measures and have a new scenario ID; otherwise `EngineMismatch` is raised.
4. **Diff.** Code computes `diff.*`: gas, grid electricity, carbon and cost versus the previous plan, plus the added, removed, blocked and conditional measures.
5. **Explain.** Recalculated what-ifs are explained by the LLM in `whatif` mode, with the same checks and patching. Declines and no-change answers (out-of-scope questions, injection attempts, only infeasible requests) use fixed template text with no LLM call, so there is nothing for an injection to steer.

## API (`api.py`)

- `POST /llm/explain {property_id, measures?, expected_scenario_id?, template_mode?, prefetch_llm?}` returns `{scenario, explanation}`. With `template_mode: true` it answers instantly and generates the LLM version in the background. The UI shows the template first, then calls again with `template_mode: false`; that second call is a cache hit.
- `POST /llm/whatif {property_id, measures?, question, expected_scenario_id?, template_mode?}` returns `{outcome, scenario_id, recalculated, scenario, explanation}`.
- `GET /llm/health` returns the provider chain, models and limits (no API calls).

The frontend sends measure selections, never numbers; the server reruns the engine. Each sentence carries `spans`: key, displayed value, status, provenance and `direction`, which the UI uses to colour rises red and falls green.

## Prompts

`backend/app/llm/prompts/`, versioned. Files are never edited in place.

| File | Use |
|---|---|
| `explain_v5.txt` | Current. v4 plus the decision context: "For you" and "Before you start" sections, permission, not-assessed and privacy rules |
| `whatif_v2.txt` | Current. v1 plus `update_context` (role, horizon, budget, priorities, constraints, done / refused measures) |
| `explain_v4.txt` | Superseded. v3 plus direction filters (`{key\|change}`), "#"-masked text facts cited by placeholder, and exact feasibility wording (infeasible = "not suitable"; needs verification = "needs checking first") |
| `explain_v3.txt` | Superseded: interaction sentence corrected; score drags "among parts with known data" |
| `explain_v2.txt` | Superseded: prose per section, rules, one worked example |
| `explain_v1.txt` | Superseded: LLM-labelled claim JSON |
| `whatif_v1.txt` | Question → structured change |
| `judge_v2.txt` | Evaluation only: sentence-level supported / unsupported / contradicted, given the scenario **and** the code-derived facts (plan order, ranked score parts, reasons) |
| `judge_v1.txt` | Superseded: the judge saw only the raw scenario, so it flagged code-derived facts such as plan order as unsupported |

## Evaluation approach

- **Suite.** `eval/make_scenarios.py` builds 115 scenarios following plan_final.md:

  | Type | Count |
  |---|---|
  | Normal | 25 |
  | Missing data | 15 |
  | Conflicting | 10 |
  | Infeasible what-if | 15 |
  | Heat pump electricity rise | 10 |
  | Insufficient data | 10 |
  | Unsupported question | 10 |
  | Prompt injection | 10 |
  | Stale scenario | 10 |

  "Dev" homes are used for prompt tuning; "heldout" homes are used only for reported numbers.
- **Deterministic checks on every case:**
  - the rendered text is complete;
  - the scenario ID matches;
  - no banned phrases;
  - warnings are passed on verbatim;
  - missing data is acknowledged;
  - infeasible measures are blocked, explained and not applied;
  - the electricity rise is stated;
  - "not estimated" appears when data is insufficient;
  - out-of-scope questions are declined without recalculation;
  - stale requests are rejected.

  Results are reported by scenario type.
- **LLM metrics:**
  - LLM-used rate (`llm` + `llm_patched`);
  - clean-LLM rate;
  - template-fallback rate;
  - **sentence acceptance**: accepted LLM sentences ÷ all LLM sentences, i.e. the share of model-written sentences that pass every grounding check;
  - template-filled sentences;
  - multi-attempt rate;
  - providers used;
  - rejections by rule;
  - latency p50/p95;
  - tokens.
- **LLM judge** (supplementary, `--judge N`, chain `--judge-providers gemini,groq`). It reports groundedness, factual accuracy and unsupported-claim rate against the brief's targets (≥90%, ≥90%, <5%). The judge sees the full numeric scenario plus the code-derived facts, and is never the generator model.
- **Human review.** 20 hard cases (`*_human_review.md`) are labelled by hand to check that the judge agrees with us.
- **Baseline.** The template-only explanations are scored with the same deterministic checks **and the same judge** (`--template-only --judge N`), on the same cases, so the LLM can be compared with a simple, fully deterministic baseline.

### Results so far (measured)

All rates carry 95% Wilson intervals in the JSON files: 100% on 10 cases only bounds the true rate above about 72%. The suite (`eval/scenarios.jsonl`) now runs on the real engine with synthetic homes, and every scenario type is in both the dev and the held-out split.

| Run | Result |
|---|---|
| Template baseline, all 131 scenarios on the **real engine**, including 16 persona cases (`llm_template_all.json`) | 100% of deterministic checks pass in every scenario type |
| What-if parsing, 40 labelled questions (`parse_eval.json`) | **LLM parser (Groq `gpt-oss-20b`): 92% exact match** (95% CI 80–97%), change F1 0.95. **Keyword baseline: 75%** (62–86%), F1 0.85. LLM misses: "do nothing at all", a request mixed with a guarantee demand, and solar plus a battery. Keyword misses: swaps, lists, unknown synonyms ("new windows"), and "keep everything" read as "add everything" |
| v3 explanations, Groq `gpt-oss-120b`, 20 dev cases, fake engine (`llm_groq_v3_dev.json`) | 20/20 LLM-written (all patched), 94.2% of 382 sentences accepted; judge on 390 final sentences: groundedness 99.5%, factual accuracy 99.5%, unsupported 0%. The judge caught one real error the checker missed (needs-verification measure called "not suitable"), now a rule |
| Template baseline judged on the same dev cases (`llm_template_judged_dev.json`, 18 cases) | groundedness 99.1%, factual accuracy 99.4%, unsupported 0.2%; the flags were the judge disputing display rounding. Judged by `gpt-oss-20b` only (Gemini quota ran out), so it is not yet like-for-like with the LLM row |

Earlier runs:

| Run | Explanations | Sentences | Live calls |
|---|---|---|---|
| Template baseline, all 115 scenarios (`llm_template_all.json`) | 100% of deterministic checks pass | — | none |
| v1: LLM-labelled claim JSON, Groq `gpt-oss-120b`, first 8 dev cases (stopped) | 1 first-pass, 2 after retry, 5 full template fallbacks | — | about 3.3k input + 3k output tokens; up to 2 calls per explanation |
| **v2: prose + code-typed sentences + patching, Groq `gpt-oss-120b`, 20 dev cases** (`llm_groq_v2_dev.json`) | **100% of deterministic checks pass; LLM used for 20/20 (3 clean, 17 patched), 0 template fallbacks, 1 call each** | **95.6% of 389 LLM sentences accepted**; 17 rejected (8 plan sentences not saying a measure needs a check, 7 warnings copied instead of cited, 2 changes without a direction), replaced by 30 template sentences | median 2.6 s (p95 3.3 s) per call; about 2.8k input + 0.76k output tokens |

The v2 gain comes from the algorithm, not from a different model: same model, same scenarios.

These are agreement results on our own documented scenarios and synthetic homes. They show the guardrails work. They are not evidence of real-world accuracy.

## How to run

```bash
venv/bin/pip install -r backend/requirements-llm.txt
venv/bin/python -m pytest -q tests/llm                                       # no API key needed
venv/bin/pip install pandas pyarrow                                          # the team engine's data loader
venv/bin/python eval/make_scenarios.py                                       # suite on the real engine (synthetic homes)
venv/bin/python eval/run_llm_eval.py --template-only                         # baseline, free
venv/bin/python eval/run_llm_eval.py --split dev --per-type 3 --providers groq   # every scenario type, live
venv/bin/python eval/run_llm_eval.py --split heldout --judge 40 --judge-providers gemini   # final numbers
venv/bin/python eval/run_llm_eval.py --template-only --split heldout --judge 40 --judge-providers gemini  # baseline
venv/bin/python eval/run_parse_eval.py --llm                                 # what-if parsing: LLM vs keywords
venv/bin/python eval/warm_cache.py && venv/bin/python eval/warm_cache.py --check   # cache the demo, then prove it
venv/bin/uvicorn dev_app:app --app-dir tests/llm --port 8000                 # dev API: real engine, synthetic homes
```

## Known limitations

- The checker is rule-based. It catches wrong numbers, directions, feasibility, unsupported comparisons, false "not estimated" claims, coverage gaps and banned wording. It cannot judge every qualitative claim: the LLM judge and human review cover that, on a sample.
- Sentence typing uses wording patterns. An unusual phrasing can be rejected (and patched from the template) even when it is correct; the reverse, a wrong number or direction getting through, is what the rules are built to prevent.
- The keyword fallback parser handles common phrasings only.
- The York data is not in git; the evaluation runs the real engine on synthetic homes. Rerun `make_scenarios.py` against York demo homes when the data is available.
- Free-tier quotas limit how much can be judged per day; the judge should be Gemini only for reported numbers (`gpt-oss-20b` shares a model family with the generator).
