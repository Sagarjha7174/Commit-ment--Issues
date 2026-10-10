# Project progress: Lloyds PS2 Green Home Score and Retrofit Recommendation Engine (Megathon X)

**Status as of 2026-10-10.** The data stage and the deterministic engine (scoring, feasibility, simulator, carbon, packages, sensitivity, audit, scenario builder, portfolio) are built, tested and pushed. Not built yet: the ML models, the property-value model, the LLM layer, the API routes, the frontend and the submission documents.

| Quick facts | |
|---|---|
| Repository | https://github.com/IIIT-ECell/megathon26-commit-ment-issues |
| Engine branch | `feature/engine-core` (pushed, head `f7bee8e`), built on `feature/engine-foundation` |
| Other remote branches | `main` (README only), `feature/engine-foundation`, `frntend` (frontend, owned by another team member) |
| Tests | **169 passed** (`pytest -q`) |
| Data checks | **9/9 PASS** (`python pipelines/check_data.py`) |
| Pull requests | none opened (by instruction) |
| Commit policy | no `Co-Authored-By` / AI attribution lines in commits or PRs |

---

## 1. Problem
Lloyds Problem Statement 2. Score a home from 0 to 100 using 7 fixed-weight components, and flag Poor and Very poor homes. Then:
- recommend **feasible** retrofits in a prioritised order;
- estimate energy savings **per fuel** (electricity and gas reported separately);
- estimate carbon reduction from documented emission factors;
- give an **indicative** property-value range.

**Core rule:** every number comes from documented models and calculations. The LLM only explains those numbers and answers what-if questions by rerunning the engine.

---

## 2. Branches and commits

### `feature/engine-foundation` (data stage)
| Commit | Content |
|---|---|
| `8a241e8` | Repo hygiene: .gitignore, .env.example, Makefile, README section for reproducing the data |
| `595e3dc` | Data pipelines and configs: York dataset build, catalogue cat-v2, score params, data checks |
| `eb3b285` | Docs and tests: data, labels, decisions, York data dictionary and mappings; unit and data-integrity tests |
| `43ec23a` | Demo homes split into a public config and internal addresses; ECUK source; duplicate `reference/` removed |

### `feature/engine-core` (engine stage, branched from foundation)
| Commit | Stage | Content |
|---|---|---|
| `1b87645` | 0 | Catalogue cat-v3: space/water gas split 0.77/0.23 (ECUK), global `heat_pump_scop` (D11) |
| `a274ca0` | 1 | Schemas, loaders, config, Green Home Score with after-retrofit state effects |
| `664266d` | 1 | Track `backend/app/data` (the `.gitignore` rule `data/` was hiding the loader package) |
| `618dae0` | 2 | Baseline selection and per-measure feasibility (D12) |
| `af5bc93` | 3 | Sequential simulator, carbon, hand-calculated reference suite, NEED combination check (D13, D14) |
| `57ab36f` | 4 | Package search with Pareto filter and featured picks, limited sensitivity, generated decision audit |
| `a671b9b` | 5 | Scenario builder (the single writer of numbers), portfolio view, hand-calculated demo fixtures |
| `f7bee8e` | 6 | API entry points, engine docs, timing |

During the session the branch history was rewritten (reset, then reword) to remove `Co-Authored-By` lines. The current remote history is clean.

---

## 3. Repository layout
```
backend/app/
  config.py                 paths + versioned config readers (no hard-coded constants)
  data/loaders.py           read-only access to homes_tagged.parquet (address columns never loaded)
  schemas/                  Pydantic v2: enums.py, property.py, retrofit.py, scenario.py
  services/
    score.py                Green Home Score + after-retrofit score
    baseline.py             baseline selection (user reading > model > NEED benchmark)
    feasibility.py          feasible / infeasible / needs_verification per measure
    units.py                gas end-use decomposition, resolved constants
    simulator.py            sequential retrofit simulator (logged, reconciled)
    carbon.py               per-fuel carbon change
    packages.py             package enumeration, Pareto, featured picks, fallbacks
    sensitivity.py          one-at-a-time sensitivity of featured picks
    audit.py                generated decision audit
    scenario_builder.py     build(request) -> ScenarioResult (only writer of numbers)
    portfolio.py            bank view: Poor/Very poor homes ranked by improvement potential
    api.py                  entry points for the API owner
configs/                    catalogue, score params/mappings, state effects, emission factors, gates, demo homes
pipelines/                  data build + score_homes.py + validate_simulator.py
tests/unit, tests/data      unit and data-integrity tests
tests/reference             hand-calculated simulator cases
tests/fixtures              hand-arithmetic demo fixtures (scenario_a/b/c.json + generator)
docs/                       DATA, LABELS, DECISIONS, SCORE, ENGINE, DEMO_HOMES, validation/, data_york/, this file
dataset/, data/             raw and built data (git-ignored, never committed)
```

---

## 4. Data stage (complete)

### 4.1 Sources (`dataset/`, not committed)
| Data | Use |
|---|---|
| EPC bulk data, England and Wales 2008–2026 (8.3 GB, via API key) | property features, ratings, assessor recommendations, addresses for matching |
| NEED anonymised data 2026 (50k and 4M homes) | metered gas and electricity, used for benchmarks (not linkable to addresses) |
| NEED Impact of measures 2026 (installation year 2023) | measured savings for loft, cavity, solid wall, solar PV, boilers, plus combinations (Table 2) |
| HM Land Registry Price Paid 2025–2026 | sale prices for the value model |
| DESNZ GHG conversion factors 2026 | carbon factors |
| DESNZ ECUK 2026 end-use tables (`configs/reference_docs/`) | gas split: space heating, hot water, cooking |

### 4.2 York dataset (`data/processed/region=york/`, not committed)
**Area:** City of York (E06000014).

| Output | Rows | Notes |
|---|---|---|
| `homes.parquet` / `homes_tagged.parquet` | 65,872 homes | canonical fields, NEED bands, baselines, flags, provenance, splits |
| `epc_certs_all.parquet` | 95,348 certificates | full history |
| `retrofit_history.parquet` | 32,051 changes | changes between a home's certificates |
| `recommendations_long` / `_wide.parquet` | 231,548 / 65,872 | assessor recommendations mapped to 7 measures |
| `sales_matched.parquet` | 4,095 sales | 4,000 linked (97.7%); EPC rating at sale, with no future leakage |
| `benchmarks.parquet` | 489 cells | NEED regional gas/electricity medians by fuel × type × rating × size |
| `monthly_synthetic.parquet` | 12,072 | **synthetic**, only to demonstrate annualisation |
| `homes_scored.parquet` | 65,872 | engine output from `pipelines/score_homes.py` |

- **Splits:** train 46,151, validation 9,797, test 9,924. Splits are by home, so no home appears in two splits.
- **Baselines:** population benchmarks, not meter readings (D6).
- **EPC age:** 32% of homes have an EPC older than 10 years.

### 4.3 Configs (`configs/`, committed)
| File | Version | Content |
|---|---|---|
| `retrofit_catalogue.json` | **cat-v3** | 7 measures: rules, impacts and their basis, sources, segment tables, costs. Globals: boiler efficiency 0.85, cooking gas share 0.0305 (ECUK), space/water split **0.77/0.23** (D11), SCOP 2.5/3.0/3.5 |
| `score_params.json` | score-params-v1 | intensity p10 75.749 / p90 186.022 kWh/m²/yr (train only, never recomputed) |
| `score_mappings.json` | score-map-v1 | weights, classes, every sub-score mapping, missing-data rules |
| `retrofit_state_effects.json` | state-effects-v1 | how each retrofit changes the recorded state for the after-retrofit score |
| `emissions_factors.csv` | DESNZ 2026 | electricity 0.14395 (includes transmission losses, D5), gas 0.18231 kg CO₂e/kWh (gross CV) |
| `feature_availability.json` | n/a | role of every column (feature, label-only, identifier, restricted address, …) |
| `demo_homes.json` | n/a | 3 public demo homes (A, B, C), no addresses |
| `value_gate.json` | n/a | value-model go/no-go, currently **`audit_pending`** |

### 4.4 Data pipelines
`build_region.py`, `epc_stream.py`, `build_catalogue.py`, `freeze_score_params.py`, `tag_homes.py`, `build_feature_availability.py`, `select_demo_homes.py`, `make_monthly_demo.py`, `annualise.py`, `audit_sales_matches.py`, `data_checks.py`, `check_data.py`. Reruns are deterministic (seed 42).

---

## 5. Engine stage (complete)

### 5.1 Conventions (apply everywhere)
- **Units:** kWh/year for energy, kg CO₂e/year for carbon.
- **Savings:** saving = before − after. Positive means a reduction; an increase is a **negative** saving.
- **Carbon:** a positive carbon value means emissions fell.
- **Missing values:** `null` plus a status (`unavailable`, `not_estimated`, `blocked`), **never 0**.
- **Provenance:** every value carries one: `observed`, `population_benchmark`, `user_provided`, `modelled`, `assumption`, `derived`, `unavailable`, `not_applicable`.
- **Privacy:** no address, full postcode, UPRN or certificate number in any output; only `display_label` and the outward postcode.

### 5.2 Stage 0: setup
- Backend skeleton, closed enums (`Provenance`, `FeasibilityState`, `MeasureId`, `MEASURE_ORDER`), Pydantic v2 schemas, loaders, config readers.
- Catalogue bumped to cat-v3 (D11).

### 5.3 Stage 1: Green Home Score (`services/score.py`, `docs/SCORE.md`)
S = Σ wₖ·sₖ, rounded half up to an integer.

| Part | Weight | Mapping |
|---|---|---|
| Energy efficiency | 0.25 | EPC SAP score, capped 0–100 |
| Energy intensity | 0.20 | 100·(p90 − x)/(p90 − p10), clipped; x = (gas + elec)/floor area |
| Insulation | 0.15 | walls/roof/floor (VP 10, P 30, A 55, G 80, VG 100), weights 0.5/0.35/0.15; elements that don't apply are skipped and the weights renormalised |
| Heating | 0.15 | heating rating on the same scale; a heat pump scores at least 75 |
| Windows | 0.10 | single 10, double 75, triple 100; partial glazing interpolated by the % multi-glazed |
| Renewables | 0.10 | none 0, some PV 60, PV covering ≥ 50% of the roof 100, +30 solar thermal, +30 wind, capped at 100 |
| Smart controls | 0.05 | none 0, timer 40, full 70, smart 100 (proxy, D4) |

- **Classes:** 80–100 Highly efficient, 65–79 Good, 50–64 Moderate, 30–49 Poor, 0–29 Very poor.
- **Missing parts:**
  - each missing part is scored 50 for the headline, and 0/100 for the range;
  - completeness is reported as k/7;
  - more than 2 missing parts makes the score unavailable.
- **After-retrofit score:**
  - only the changed parts are recomputed;
  - the EPC SAP score is **not re-assessed**, so that part is labelled unchanged;
  - an unknown state stays unknown;
  - states are never downgraded.

**Results (train split):**

| Class | Homes | Share |
|---|---|---|
| Highly efficient | 1,754 | 3.8% |
| Good | 7,925 | 17.2% |
| Moderate | 27,500 | 59.6% |
| Poor | 8,786 | 19.0% |
| Very poor | 149 | 0.3% |
| unavailable | 37 | 0.1% |

- **Mean score by EPC band:** A 79.6, B 75.1, C 61.1, D 53.1, E 45.9, F 40.7, G 30.5 (falls in order).
- **Completeness:** 39,694 homes have 7/7. Missing parts are mostly renewables (5,735 homes, PV not recorded on old EPCs) and intensity (3,080, gas baseline unavailable).

**Hand-checked: demo A (1967–75 detached house, EPC E)**
- Parts: 12.000 + 6.816 + 3.265 + 12.000 + 6.655 + 0 + 3.500 = **44.24 → 44, Poor**.

### 5.4 Stage 2: baseline and feasibility (`baseline.py`, `feasibility.py`)
- **Baseline priority:**
  1. user reading
  2. modelled energy (only if `configs/model_switch.json` says the model beat the benchmark; default off)
  3. NEED benchmark
- **Blocking flags:** gas boiler without mains gas, zero or negative EPC energy, no heating description. Each makes improvement potential unavailable.
- **Feasibility:** feasible, infeasible or needs_verification, with a High/Medium/Low suitability, reason code, reason text and missing inputs. Missing critical input gives needs_verification, never infeasible (D12).

Feasibility counts (train split):

| Measure | Feasible | Infeasible | Needs verification |
|---|---|---|---|
| Loft | 13,358 | 32,767 | 26 |
| Cavity wall | 11,469 | 34,483 | 199 |
| Solid wall | 8,654 | 37,298 | 199 |
| Double glazing | 4,966 | 41,161 | 24 |
| Smart thermostat | 43,217 | 2,897 | 37 |
| Heat pump | 45,536 | 536 | 79 |
| Solar PV | 31,020 | 11,739 | 3,392 |

### 5.5 Stage 3: simulator and carbon (`simulator.py`, `units.py`, `carbon.py`, `docs/ENGINE.md`)
- **Gas decomposition:**
  - cooking gas = 3.05% of gas, never changed;
  - the remaining heating and hot-water gas is split 0.77 space heating / 0.23 hot water;
  - useful heat = gas × 0.85.
- **Converting each type of impact:**

| Impact type | Measures | How it is applied |
|---|---|---|
| % of total gas | loft, cavity, solid wall (NEED) | kWh saved = impact × current total gas, converted into a fraction of space-heating gas (capped at 1) |
| % of space-heating demand | glazing, thermostat (brief ranges) | applied directly; partial glazing is scaled by the single-glazed share |
| % of grid electricity | solar PV (NEED) | applied to (electricity + heat-pump electricity) |
| anything else | n/a | `not_estimated` |

- **Fixed order:** loft → cavity → solid wall → glazing → thermostat → heat pump → solar. Reductions multiply.
- **Heat pump:**
  - **full:** removes space and water gas;
  - **partial:** replaces a declared share;
  - **unknown:** the engine abstains;
  - added electricity = useful heat ÷ SCOP 3.0, which shows as a negative electricity saving.
- **Solar:** applied last; reduces grid import only.
- **Reconciliation:** every step is logged, and for each fuel the steps must add up to the total (asserted).
- **Improvement potential:** 100 × (purchased before − after) / before. It is unavailable if the baseline is zero, missing or blocked, and not estimated if no measure could be estimated.
- **Carbon:** ΔE_gas × 0.18231 + ΔE_elec × 0.14395.
- **Reference suite:** 14 hand-calculated cases in `tests/reference/simulator_cases.json`:
  - 3% of 12,000 kWh = 360 kWh;
  - loft + cavity saves less than the sum of the two alone;
  - fabric order doesn't change the total;
  - full, partial and unknown heat-pump modes;
  - solar applied last;
  - an infeasible measure is blocked;
  - a zero baseline gives "unavailable";
  - an unsupported impact type gives "not estimated";
  - carbon signs are correct.

**Validation against NEED combination figures** (`pipelines/validate_simulator.py`, tolerance ±5 pp):

| NEED combination | NEED median | Simulated | Gap |
|---|---|---|---|
| Cavity + loft | 8.38% | 14.81% | +6.43 pp |
| Solid wall + loft | 14.31% | 19.93% | +5.62 pp |
| Solid wall + heat controls | 9.15% | 21.58% | +12.43 pp |
| Solid wall + loft + heat controls | 10.27% | 24.04% | +13.76 pp |

All four are **outside tolerance**: the simulator overestimates combinations. The model was not tuned to fit, and a warning is attached to combined packages (D14).

### 5.6 Stage 4: packages, sensitivity, audit (`packages.py`, `sensitivity.py`, `audit.py`)
- **Enumeration:** every combination of measures that are feasible or need verification and can be estimated (at most 128), including do-nothing.
  - Cost = catalogue mid.
  - A package is *confirmed* if every measure is feasible, and *conditional* if any measure needs verification (with what to verify).
- **Pareto filter:** cost lower, carbon saving higher, purchased-energy saving higher.
- **Featured picks** (taken from confirmed, non-dominated packages):
  - lowest cost cutting emissions by at least 10%;
  - largest carbon saving;
  - most carbon saved per pound among packages cutting at least 10%.
- **Ties:** larger carbon saving, then lower cost, then fewer measures, then package id.
- **Fallbacks** (each explicit; the threshold is never lowered silently):
  - no package reaches 10%;
  - no valid cost data;
  - no package cuts emissions;
  - only conditional packages;
  - baseline unavailable.
- **Sensitivity:** 10 one-at-a-time runs: baseline ±15%, SCOP 2.5/3.5, gas split 65/35 and 85/15, cooking share ×½ and ×2, impacts low/high.
  - Reports whether each featured pick survives.
  - Labelled "not a confidence interval".
- **Decision audit:** generated from the result. It covers the baseline, feasibility, excluded and dominated packages, conditional packages, the winner and an alternative, the factors separating them, survival under sensitivity, the unknowns and the versions.

### 5.7 Stage 5: scenario builder and portfolio (`scenario_builder.py`, `portfolio.py`)
- **`build(request)`** is the **only writer of numbers**. Its steps:
  1. home
  2. baseline
  3. feasibility
  4. simulate
  5. carbon
  6. score before and after
  7. packages
  8. sensitivity
  9. valuation (gated)
  10. audit
- **Scenario ID:** SHA-256 of the home state, the request and the config versions; timestamps are excluded. The same request gives the same ID, and any change gives a new one.
- **Blocked measures** never get a computed impact.
- **Demo fixtures:** `tests/fixtures/hand_calc_demo.py` computes the expected numbers for demos A, B and C by hand arithmetic, without importing the engine. The engine reproduces them to within 1e-6.

**Gate 2: demo home A, end to end**

| Item | Value |
|---|---|
| Baseline | gas 21,616.7, electricity 3,766.7 kWh (NEED benchmark) |
| Score | 44 Poor before → **75 Good** after (EPC not re-assessed) |
| Step savings (gas / electricity, kWh) | loft 694.3 / 0; cavity 2,506.9 / 0; glazing 168.2 / 0; thermostat 957.6 / 0; heat pump 16,630.4 / **−4,712.0**; solar 0 / +1,036.8 |
| Package | gas −20,957.4, electricity **+3,675.2** (negative saving); purchased energy 25,383 → 8,101 kWh; **improvement potential 68.1%** |
| Carbon | gas +3,820.7, electricity −529.0, **total 3,291.7 kg/yr (73.4% of baseline)** |
| Featured: lowest cost ≥ 10% | cavity wall, £1,000, 472 kg (10.5%), survives 9/10 runs |
| Featured: largest carbon saving | all 6 feasible measures, £29,350, 3,292 kg, survives 10/10 runs |
| Featured: carbon per pound | cavity wall, survives 7/10 runs |
| Valuation | not estimated: "audit pending" (value gate closed) |

**Demo B** (flat, electric heating):
- Score 61, Moderate.
- Loft, walls, glazing and solar are infeasible.
- Thermostat and heat pump are feasible but not estimated (D13).
- Improvement potential: "not estimated".

**Demo C** (missing data):
- Score unavailable (completeness 1/7).
- Every measure needs verification.
- Baseline unavailable, so improvement potential is unavailable.

**Portfolio (all 65,872 homes):**
- **Counts by class:**

| Class | Homes |
|---|---|
| Highly efficient | 2,453 |
| Good | 11,263 |
| Moderate | 39,440 |
| Poor | 12,431 |
| Very poor | 229 |
| unavailable | 56 |

- **Flagged Poor or Very poor:** 12,660 homes. 11,277 have an improvement potential; 1,383 are unavailable.
- **Median improvement potential:** 65.4%, driven mostly by heat pumps.
- **Total carbon saving potential:** 17,753 t/yr. This is overstated, because of D14.
- **Incomplete data:** 13.9% of homes.

### 5.8 Stage 6: hardening
- `compileall` is clean.
- Entry points are in `services/api.py` (§9).
- Timing over 300 random test homes:

| Call | p50 | p95 | max |
|---|---|---|---|
| `build()` | 1.2 ms | 2.9 ms | 5.6 ms |
| `build()` with sensitivity | 5.7 ms | 22.9 ms | 52 ms |
| `portfolio()` over all homes (cached after first call) | | | about 5 s |

---

## 6. Decisions log (`docs/DECISIONS.md`)
| ID | Decision |
|---|---|
| D1 | Study area = City of York |
| D2 | Benchmarks split by main heating fuel |
| D3 | Secondary glazing counted as double |
| D4 | "Smart controls" = time-and-temperature zone control proxy |
| D5 | Electricity factor includes transmission and distribution losses (0.14395) |
| D6 | Baselines are population benchmarks, not meter readings |
| D7 | EPC `energy_consumption_current` unit unverified; deprecated column not used |
| D8 | Retrofit costs from EPC indicative-cost text |
| D9 | Gas end-use shares split into three quantities |
| D10 | Value-model gate (audit precision ≥ 0.90, ≥ 500 matched sales) |
| D11 | Space/water gas split 0.77/0.23 (ECUK); catalogue cat-v3; global SCOP |
| D12 | Unknown wall or roof type → needs_verification; "dwelling above" → loft infeasible |
| D13 | Non-gas-heated homes: fabric, glazing and thermostat savings not estimated; heat pump not estimated |
| D14 | Simulator overestimates NEED combinations; not tuned; warning attached |

---

## 7. Tests and quality
| Test file | Tests | Covers |
|---|---|---|
| `tests/unit/test_score.py` | 41 | weights, class boundaries, rounding, monotonicity of every mapping, missing parts and ranges, after-retrofit rules, demo A hand check, A-rated scores above G-rated |
| `tests/unit/test_feasibility_baseline.py` | 18 | baseline priority, blocking flags, both sides of each rule, missing input → needs_verification, demo homes |
| `tests/unit/test_simulator.py` | 23 | 12 reference cases plus 360 kWh, multiplication, fabric order, reversibility, reconciliation, unsupported impact type, impact levels |
| `tests/unit/test_packages.py` | 23 | 11 hand-built optimum cases, each fallback, determinism, Pareto, warnings, sensitivity |
| `tests/unit/test_scenario_builder.py` | 17 | scenario ID stability and change, blocked measures, no address, user reading, valuation gate, audit, under 1 s, demo A/B/C vs hand fixtures |
| `tests/unit/test_portfolio.py` | 2 | ranking, unavailable never 0, no address |
| `tests/unit/test_catalogue.py`, `test_score_params.py`, `test_annualise.py`, `test_audit_sales.py` | 36 | foundation configs and pipelines |
| `tests/data/test_data_integrity.py` | 9 | the 9 data checks |
| **Total** | **169** | all passing |

---

## 8. How to run
```bash
python -m venv .venv
.venv/bin/pip install pandas pyarrow duckdb rapidfuzz odfpy openpyxl tabulate pytest "pydantic>=2.7"
make data-rebuild        # needs dataset/ raw files
make data-check          # 9 data checks
make score               # score all homes -> homes_scored.parquet + distribution
make validate-sim        # simulator vs NEED combinations -> docs/validation/
make test                # all tests
.venv/bin/python tests/fixtures/hand_calc_demo.py   # regenerate hand fixtures
```

---

## 9. Entry points for the API owner (`backend/app/services/api.py`)
`backend/app/main.py` does not exist yet.

```python
build(req: ScenarioRequest) -> ScenarioResult
assess(home_id: str) -> list[FeasibilityItem]
score(home_id: str) -> ScoreResult
search(home_id, assumptions=None, threshold_pct=10.0, budget_gbp=None, user_reading=None) -> PackageSearch
portfolio(top_n: int = 50, split: str | None = None) -> dict
```

- **`ScenarioRequest` fields:**
  - `home_id`
  - `measures`: None means every non-infeasible measure
  - `assumptions`: impact level, SCOP, gas split, cooking share, boiler efficiency, heat-pump mode and share, baseline scale
  - `user_reading`: gas and electricity kWh
  - `include_packages`
  - `include_sensitivity`
- **What-if:** change the request, call `build()` again, and give the LLM the new `ScenarioResult` JSON.

---

## 10. Coverage of the judging criteria
| Criterion | Weight | Status |
|---|---|---|
| Business relevance of recommendations | 10% | Done: featured packages, portfolio ranking, suitability and reasons |
| Green Home Score and insight | 15% | Done |
| ML and recommendation quality | 20% | **Gap:** rules-based engine only; no trained model or comparison against a simple baseline |
| Savings, carbon, property value | 15% | Savings and carbon done; **value not done** (gate closed) |
| GenAI and LLM | 15% | **Not started** (engine output and audit are ready for it) |
| Technical architecture | 10% | Engine, tests and docs done; API, diagram and dependency file missing |
| Explainability and Responsible AI | 5% | Provenance, audit and warnings done; RAI note missing |
| UX and dashboard | 5% | Not in this branch (`frntend` branch exists) |
| Innovation (customer memory) | 5% | Not started |

---

## 11. What is left

### 11.1 Manual tasks
1. **Value audit:** fill the `correct` column (1/0) for all 50 rows of `data/processed/region=york/match_audit_sample.csv`, run `.venv/bin/python pipelines/audit_sales_matches.py`, and commit `configs/value_gate.json`.
2. **Merging:** decide on PRs to `main` for `feature/engine-foundation` and `feature/engine-core`.
3. **Hashing IDs:** decide whether `home_id` should be hashed before it reaches the API (§13).

### 11.2 Build work
| Item | Owner | Detail |
|---|---|---|
| Property-value model | P2 or ML | Sale-price regression on property features, rating and location (4,000 matched sales). Compare the same home before and after with everything else held constant; report a range; call it indicative, not causal. Enable only once the gate passes. |
| Energy model | ML | LightGBM on NEED to predict gas and electricity from property bands. Compare against the benchmark; enable through `configs/model_switch.json` only if it is better. |
| Recommendation model | ML | Learn assessor recommendations (`rec_*` labels). May only reorder feasible measures. Report precision/recall and ranking metrics against the rules-only baseline. |
| LLM layer | LLM | Prompts receive only the `ScenarioResult` and audit JSON. A number checker rejects any figure not in the JSON. What-if → new `build()`. Held-out evaluation set covering missing data, conflicts, infeasible measures and electricity rising after a heat pump. Targets: ≥ 90% grounded, ≥ 90% accurate, < 5% unsupported claims. |
| API | API | FastAPI routes over `services/api.py` |
| Frontend | Frontend | Score gauge, part contributions, package list, per-fuel savings, carbon, warnings, chat |
| Customer memory (optional) | Open | Completed retrofits become infeasible and stated constraints (e.g. a budget) apply, then `build()` reruns; show how recommendations change |
| Submission documents | Team | Architecture diagram, evaluation report, Responsible AI note, held-out test predictions with schema and labels, run instructions |
| Packaging | P2 | `requirements.txt` / `pyproject.toml`; CI running tests and data checks |

---

## 12. Drawbacks (limits of the current approach)
1. **Benchmark baselines.** Savings describe a typical home of that type in the region, not the actual household (D6).
2. **Combinations are overestimated** by 5.6–13.8 pp against NEED (D14). Package savings and the portfolio carbon total are optimistic.
3. **Unvalidated impacts.** Glazing, thermostat and heat pump use the brief's ranges or assumptions; they are flagged in outputs.
4. **Non-gas homes (about 18%)** get no fabric or heat-pump savings estimate (D13).
5. **Intensity overlaps with the EPC rating**, because benchmark groups are partly defined by EPC band. A user meter reading removes this.
6. **EPC not re-assessed after retrofit.** The after-score understates the gain in the energy-efficiency part.
7. **Smart-controls proxy.** Zone control is used as a stand-in, not real smart-thermostat data (D4).
8. **Costs are indicative.** They come from EPC software text, not real quotes; the heat-pump cost is a single value from 31 records.
9. **National averages.** Gas end-use shares and boiler efficiency are not specific to York or the home.
10. **Not modelled:** weather, occupancy, rebound, ventilation, thermal bridges, PV orientation, heat-pump sizing, tariffs. It is an accounting model, not a digital twin.
11. **York only.** Rebuilding the data is needed for any other area.
12. **Headline impacts only.** The catalogue's impacts by EPC band, age, type and region are not used yet.
13. **No property value yet.**

---

## 13. Known issues
| Issue | Severity | Action |
|---|---|---|
| `home_id` looks like "U" + UPRN (an address-linked identifier), e.g. `U100050529765` | Medium (privacy) | Hash at the API boundary, or rebuild the IDs |
| Value gate closed (`audit_pending`, 0/50 rows filled) | High (judging) | Fill in the audit |
| No `requirements.txt` / `pyproject.toml`; Pydantic installed by hand | Medium | Add a dependency file |
| Demo C foundation note says "loft infeasible"; the engine says needs_verification (roof is `SAP05:Roof`) | Low | Explained in D12; update `DEMO_HOMES.md` |
| Demo A after-score is exactly 74.5, on a rounding boundary | Low | Rounds half up to 75; config changes could flip it |
| Model-switch file is read but no model output is connected | Expected | The ML owner connects it |
| The portfolio is computed on first call (about 5 s) and cached in memory | Low | Precompute in a pipeline |
| Scripts that produced `need_*.parquet` and `ppd.parquet` are not in the repo (rules in `DATA.md`) | Medium (reproducibility) | Add the scripts |
| `epc_predicted_consumption_kwh_m2_primary` is deprecated | Info | Engine never reads it; use `epc_modelled_energy_kwh_m2` |
| Uncommitted schema changes were lost once by a `git reset --hard` | Resolved | Re-applied and committed |

---

## 14. Improvements (prioritised)

### Biggest gain for judging
1. **Value audit and value model**, to unlock the property-value range.
2. **ML layer** (energy model and recommender), each with a comparison against a simple baseline. This is the 20% criterion.
3. **LLM with a number-grounding checker** and a held-out evaluation set.

### Accuracy
4. ~~Use the catalogue's **impacts by segment**~~: done in engine-v2 (D15).
5. ~~Add a **NEED-calibrated combination factor**, shown alongside the multiplicative model~~: done in engine-v2 (D17).
6. ~~Add an **electric-heating end-use split**~~: done in engine-v2 (D16); run `make elec-split` to build the split file.
7. Use **PVGIS** for solar yield by orientation instead of a flat 12.2%.
8. Collect **user meter readings** in the UI (already supported by the engine).

### Engineering
9. Dependency file, CI, pre-commit hook.
10. Precompute the portfolio into parquet.
11. Hash IDs at the API boundary.
12. Architecture diagram and evaluation report built from the existing test and validation outputs.

### Innovation
13. Customer memory: completed retrofits, a budget and preferences, then rerun `build()` and show how recommendations change.

---

## 15. Never committed
`.env` (API key), `dataset/`, `data/` (built parquet files, audit sample with addresses, `demo_homes_internal.json`), real addresses and full postcodes.

---

## 16. engine-v2 refinements (branch `feature/engine-improvements`)
| ID | Refinement | Status |
|---|---|---|
| D15 | Segment-aware NEED impacts (EPC band, age, type, region; empirical-Bayes shrinkage) | on by default |
| D16 | Electrically heated homes: heating share of electricity from NEED benchmarks; fabric, glazing, thermostat and heat pump estimated on electricity | code done; **run `make elec-split`** (needs `benchmarks.parquet`) and commit `configs/electric_heating_split.json` |
| D17 | NEED-calibrated reference next to the engineering estimate for 2+ fabric/controls measures | `configs/combination_calibration.json` built and committed |
| D18 | Boiler efficiency from the EPC heating rating (heat-pump electricity) | on; values are an assumption to verify against SAP 10.2 Table 4b |

- **Sensitivity:** 12 runs (adds headline impacts and NEED-calibrated combinations).
- **Tests:** 185 unit tests pass, 10 are skipped without data, and there are 9 data checks. New tests are in `tests/unit/test_improvements.py`.
- **Demo A** (hand-checked): improvement potential 68.60%, carbon 3,310.6 kg/yr (engineering); NEED-calibrated reference 3,216.8 kg/yr.

**To do on the data machine:**
- `make elec-split`, then commit `configs/electric_heating_split.json`.
- `make test`: the demo tests need data. Demo B's fixture expects "not estimated" until the split file exists; regenerate it with `tests/fixtures/hand_calc_demo.py` after building the split, and extend demo B's expectations to the estimated values.
- `make score` and `make validate-sim`.

---

## 17. engine-v3 (branch `feature/engine-improvements`): see docs/IMPROVEMENT_PLAN.md
| Phase | Content | Status |
|---|---|---|
| A | PV basis (D19), roof-aware loft rule + planning note (D20), segment max rule (D15 rev.), partial glazing cost (D23), field SCOP 2.80 (D24), thermostat by controls (D25) | done |
| A2 | `make engine-cal`: area elasticity (D21), missing-part priors (D22), segment backfit, York reference area, baseline spread, score params v2 | code done; **run on the data machine** |
| B | bills at the Ofgem cap (D26), BUS grants, net-cost selection, payback, illustrative loan (D27) | done |
| C | Monte Carlo ranges (D28), portfolio fabric-only potential and `rank_by` (D29) | done |
| D | post-retrofit SAP model, value model, ML, LLM, API, dashboard, planning data, lifetime carbon | not started |

- **Tests:** 249 unit tests pass, 10 are skipped without data, and there are 9 data checks.
- **New test files:** `tests/unit/test_engine_v3.py` and `tests/unit/test_engine_calibration.py`. The latter includes an end-to-end run of the calibration pipeline on synthetic files.

**On the data machine, in order:**
```bash
make engine-cal && make elec-split
.venv/bin/python tests/fixtures/hand_calc_demo.py
make test && make validate-sim && make score
git add configs/ && git commit -m "Engine calibration from York/NEED data" && git push
```
The calibration changes demo A's numbers (area scaling, backfitted segments). Run the fixture script after it, then review the diff of `tests/fixtures/scenario_a.json`.
