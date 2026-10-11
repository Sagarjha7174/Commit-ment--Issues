# Failure analysis across the system (2026-10-11)

Every layer was run on the real York build (65,872 homes) and its failures traced to a cause. Each item gives the
evidence (command or file), the cause, and its status: **fixed** (with the commit's test) or **open** (with the
recommended next step). Decisions: D44–D45.

## 1. Checks run

| Check | Before | After |
|---|---|---|
| `make test` (backend, real data; the 37 data-dependent tests run) | 728 passed, 0 skipped | 757 passed, 0 skipped (data-integrity tests now collected) |
| `make data-check` | 9/9 pass | 9/9 pass |
| `make web-test` (typecheck, lint, Vitest) | 65/65 | 73/73, lint clean |
| `make validate-sim` | 4/4 NEED combinations outside ±5 pp (known, D14/D17) | unchanged (not tuned) |
| `make web` + HTTP checks (`/api/health` = `york_parquet`; `/api/portfolio` for all 4 `rank_by`; one test home per EPC band A–G; `/llm/explain` scenario id = `/api/scenario`) | – | all pass |

## 2. Data

| Finding | Evidence | Cause | Status |
|---|---|---|---|
| 32.4% of homes (21,358) have a latest EPC older than 10 years | `homes_tagged.flag_stale_epc` | homes not sold or let since then have no newer certificate | open (data limit): every scenario warns; a customer's own data should replace stale fields |
| 4,415 homes (6.7%) had improvement potential unavailable; 8% of a 300-home test sample had no baseline, so no savings | `make data-check`; engine sample | 4,203 of them are not gas-heated (electric 2,322, other 1,392, heat pump 476): no gas to save, and the electric split was off (D30) | **mostly fixed** (D46): electric split applied; Poor/Very poor homes with potential unavailable 1,383 → 611; the rest (oil, other, unknown heating) stay "not estimated", never 0 |
| NEED cannot be linked to York homes | DATA.md 1.2 | anonymised data | open: energy accuracy on York homes is unmeasurable |

## 3. Scoring and engine

| Finding | Evidence | Cause | Status |
|---|---|---|---|
| **17% of homes got no fabric/glazing/controls savings estimate** (electric 12.9%, other 3.1%, oil 1.0%); in a 300-home test sample 18% had measures applied but none estimated | engine sample; demo B | D13: NEED impacts are % of gas; the electric-heating split (D16) existed but was **off** (D30) | **fixed for electric homes** (D46): split applied, hand-calculated fixture B and reference cases redone by hand; test sample 18% → 4%. Oil and other heating stay not estimated (no metered baseline). Engine calibration (`engine_calibration.json`, score params v2) still not applied (D30) |
| Simulated combined packages exceed NEED measured medians by 5.6–13.8 pp | `make validate-sim` | multiplicative engineering model vs in-use effects | open by design (D14/D17): the NEED-calibrated figure is shown next to the engineering one |
| Score is monotonic by EPC band (A 79.6 … G 30.7); 56 homes have no score (>2 parts missing) | `homes_scored.parquet` | – | ok |
| Four engine tests failed at the start of the ML phase | D30/D39 | stale expectations (demo A's flat roof under D20; a re-scored file) | fixed earlier (D39) |

## 4. ML models

| Finding | Evidence | Cause | Status |
|---|---|---|---|
| **A heat pump's modelled EPC change was wrong for electric homes, and the earlier diagnosis ("the SAP model understates heat pumps") was wrong.** Electric test homes: heat pump alone ΔSAP +0.5 (39% negative) vs observed storage heaters → heat pump pairs +11.8 | `ml_cert_states` pairs; engine sample | not the model: on real after-certificates it matches observed changes (boiler → heat pump: train +7.4 vs +6.7, test +7.6 vs +9.8; storage heaters → heat pump +11.3 vs +11.8). The engine's after-state kept the old heating rating, so electric homes were modelled as a heat pump rated Very Poor, a state no certificate has | **fixed** (D46): after a heat pump the heating rating is at least Good and controls at least full, as on York heat-pump certificates; electric homes +12.4 (none negative). Gas homes: small modelled fall (median −2.9), consistent with SAP's cost basis; only 10 pure swaps, too few to calibrate. The "heat pump can lower the EPC" caveat is now given only when the heat pump replaces gas. No retraining |
| SAP error is highest at EPC F/G (MAE 9–10 vs 3.5) and A | `ml_slices.json` | few homes, extreme states | open: flagged in the model card |
| Value error is highest for flats (MdAPE 15% vs 9%) | `ml_slices.json` | leasehold, block-level variation not observed | open: flagged in the model card |
| Energy model (NEED) fails its gate (1.5–1.6% < 2% gain) | `ml_energy.json` | banded NEED features leave little signal beyond cell medians | handled: benchmark kept; quantile models ship |
| Recommender: heat pump has 23 training labels; high scores reflect assessor rules on the same fields | `ml_recommender.json` | label source | handled: rules only for heat pumps; agreement labelled "consistent with the EPC assessor" |

## 5. LLM layer

| Finding | Evidence | Cause | Status |
|---|---|---|---|
| Parse model read explicit requests as "no change" (q29 add heat pump, q44 add double glazing) and dropped a stated budget (q40) | `llm_eval_llm_attempt1_quota.json` | LLM misreading; no cross-check | **fixed** (D44): keyword safety net (`llm+keywords`), stated context kept; tests `test_llm_safety_net.py` |
| `gpt-oss-20b` parses always failed validation and silently used the keyword parser | call log `invalid_output … priorities: Input should be a valid array` | the model returns `null` for empty lists | **fixed**: null list = empty list; test |
| Grammar broken in patched answers ("with the SAP score goes up by 23 points") | live answer | `{key\|change}` renders a code verb phrase inside the LLM's own sentence | **fixed** (D45): no filters in LLM sentences (`FILTER`), prompt `explain_v7`; test |
| Fragments without labels or full stops ("Key issues:" lost) | live answer | bare `{derived.issues}` sentences; dropped sentences not replaced | **fixed** (D45): `FRAGMENT` rule, replacement by the template sentence citing the same facts, full stop on every sentence; tests |
| Benchmark caveat twice; on some homes missing entirely | template output | wording checks read unrendered text; the benchmark pattern matched "typical published ranges" | **fixed** (D45): wording checks read cited warnings, tighter pattern, one caveat per topic; tests |
| Payback and the illustrative loan could be omitted | coverage rules | not required | **fixed** (D45): coverage + template fill; test |
| A rising score/SAP shown red like rising energy use | UI | colour from arithmetic direction | **fixed** (D45): span `sentiment`; backend and frontend tests |
| The browser template said "Bills in pounds are not estimated" next to engine bills | `explainTemplate.ts` | written before D26/D27 | **fixed**: engine bills, grants, payback, loan; tests |
| The test suite made real LLM calls (and spent quota) | call log during `make test` | `test_web_api.py` posts with `template_mode`, whose default background prefetch called the LLM; only `tests/llm` disabled providers | **fixed**: root conftest disables LLM and its cache |
| The committed "real LLM" evaluation was 51/53 template answers | `llm_eval_llm_attempt1_quota.json` | provider daily quotas exhausted; the run did not stop | **fixed**: the eval stops on quota and never reports a mostly-template run |
| Prompts too large for free tiers (≈6.6k input tokens per explanation) | call log | detail facts the template already covers were in the prompt | **fixed**: standalone rows, ranking list and package money details hidden from the LLM (still valid keys): ≈4.1k → 2.7k user tokens |

## 6. Real-LLM evaluation

`docs/LLM_EVALUATION.md` (from `docs/validation/llm_eval_llm.json`), Groq `gpt-oss-20b` / `qwen3.8-27b` then Gemini
`3.1-flash-lite`: 53/53 items pass every check; groundedness 100% (401 numbers), factual accuracy 100% (198 cited),
unsupported-claim rate 0% (720 sentences), what-if success 100% (17), refusal correctness 100%. Sources: 1 LLM, 41 LLM
patched with template sentences, 11 template (9 by design: declines, refusals, blocked measures). The checker
rejected 183 of 979 LLM sentences (acceptance 81.3%).

| Finding | Evidence | Cause | Status |
|---|---|---|---|
| q20 and q40 fell back to the template ("[WORDING] say that the figures are estimates, not guarantees") | replay of the cached LLM answers | `dedupe_claims` gave each sentence only its first caveat topic, so an LLM sentence saying "benchmark ... and estimates, not guarantees" was dropped as a benchmark repeat, losing the only estimates caveat | **fixed** after the run (disclosed): a sentence is dropped only if every caveat it carries is kept elsewhere; test; replay gives LLM answers |
| The first real-LLM attempt answered 51/53 from the template | `llm_eval_llm_attempt1_quota.json` | daily quotas of the default models | handled: not reported; the run used other free-tier models via environment variables |
| Median 60 s per item | run summary | free-tier rate-limiter waits, not model time | open: paid tier or a committed answer cache for the demo |

## 7. Other findings from the implementation report (2026-10-11)

| Finding | Evidence | Status |
|---|---|---|
| `make test` never ran `tests/data/` (9 data-integrity tests) | `pytest.ini` `norecursedirs = ... data ...` also matched `tests/data` | **fixed**: folder renamed `tests/data_integrity`; `make test` collects 757 tests |
| Home ids are `U` + UPRN for most homes and appear in URLs, API responses and `eval/test_predictions.csv`; the API docstring said no response carries a UPRN | `pipelines/build_region.py`, `main.py` | **decided** (D47): ids kept (UPRNs are published with every certificate in the open EPC register, OGL; changing ids would change the hashed splits); the docstring now states what is true |
| The web app offered SCOP 2.5 / 3.5 and the method page showed 2.5 / 3.0 / 3.5, while the engine uses 2.44 / 2.80 / 3.5 (D24) | `TryTab.tsx`, `ScenarioLab.tsx`, `evidence.py`, snapshot presets | **fixed**: `/api/evidence` reports the engine's SCOP; both controls and the snapshot presets read it |

## 8. Test counts

| Suite | Before (start of this task) | After |
|---|---|---|
| Backend `make test` (real data) | 728 passed (data-integrity tests not collected) | 757 passed (unit 446, LLM 302, data integrity 9) |
| Data checks (`make data-check`) | 9/9 | 9/9 |
| Frontend `make web-test` | 65 passed | 73 passed; typecheck and lint clean |

## 9. Still open (not fixable without new data or retraining)

- Stale EPCs (32%), NEED not linkable to York homes, oil/other heating without a metered baseline: data limits, disclosed.
- Simulated stacked fabric savings above NEED by 5.6-13.8 pp: by design (D14/D17), the NEED-calibrated figure is shown next to it.
- SAP error at EPC A/E/F/G and value error for flats: weak slices of trained models, flagged in the model cards; fixing them needs retraining and a new test evaluation.
- Engine calibration (area scaling, missing-part priors, score params v2): built, not applied (D30); applying it changes every home's numbers and the hand-calculated fixtures A and C.
- Live LLM latency (~60 s per answer on free tiers).
