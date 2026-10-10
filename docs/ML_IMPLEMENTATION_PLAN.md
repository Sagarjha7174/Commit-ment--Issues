# ML implementation plan (Phase D): Lloyds PS2 Green Home Score

Audience: the coding agent that runs on the data machine (it has `data/` and `dataset/`). Read this whole file before
writing code. Execute the milestones in order. Each milestone ends with tests, a commit and a short report.

Judging weights this phase serves:
- **ML and recommendation quality (data quality, validation methodology, held-out metrics): 20%**;
- property value, part of "Energy savings, carbon reduction and property-value estimation" (15%);
- explainability, reproducibility and architecture.

The brief scores **validation methodology and comparison with a simple baseline**, not model sophistication. A model
that does not beat its baseline on validation **is not shipped**: the engine keeps the baseline and the report says so.

---

## 0. Ground rules (non-negotiable)

1. **Privacy.**
   - Never load, print, log, commit or return EPC address columns or full postcodes. The forbidden columns are the `restricted_address` role in `configs/feature_availability.json`: `address`, `address1-3`, `raw_address1-3`, `raw_posttown`, `postcode`, `posttown`, plus `paon`, `saon`, `street`, `sale_addr*` and `epc_address` in the sales table.
   - Drop these columns immediately after reading any parquet file.
   - Outward postcode (e.g. `YO31`) and postcode sector (e.g. `YO31 1`) may be used as location features.
   - `match_audit_sample*.csv` is never read or committed.
2. **Leakage.**
   - **Features:** only `feature_ok` columns (plus features parsed from description text available on the certificate, see §2), and only values known at prediction time. Never use `label_only` columns (`potential_*`, `rec_*`, `n_recommendations`, `has_recommendations`) as features.
   - **Value model:** features come from the certificate lodged **on or before the sale date** (`epc_cert_at_sale`), never from the latest certificate.
   - **Splits:**
     - by home, using the existing `split` column (train / val / test, 70/15/15, hashed `property_id`); never re-split;
     - NEED has its own `split` column;
     - all encoders, target encodings, priors, scalers and tuning use **train only**;
     - cross-validation inside train uses `GroupKFold` on `property_id` (for the value model, on postcode sector as a spatial check as well).
   - **The test split is scored exactly once**, at the end (M7), after every choice has been frozen on validation.
3. **Engine contract.**
   - The deterministic engine (`backend/app/services/scenario_builder.build`) stays the only writer of numbers.
   - Models plug in as services whose outputs carry `provenance = "modelled"`.
   - Missing values stay `null` plus a status, never 0.
   - Every model has a version string that enters `config.versions()`, so the scenario id changes when a model changes.
4. **Reproducibility.**
   - Seed 42 everywhere; deterministic LightGBM settings (`deterministic=True`, `force_row_wise=True`, `num_threads` fixed).
   - Pinned dependency versions in `requirements.txt`.
   - Every pipeline rerunnable with one `make` target.
5. **Artifacts.**
   - Models are saved as **LightGBM text** (`models/<name>/model.txt`) plus `models/<name>/meta.json` (features, categories, version, training data hash, metrics, params). Both are committed, so judges can rerun inference.
   - Large prediction tables go to `data/processed/region=york/*.parquet` (git-ignored).
   - Metrics JSON goes to `docs/validation/` (committed).
6. **Git.**
   - Branch `feature/ml` from `feature/engine-improvements`, **after** M0 step 1.
   - Commit per milestone with clear messages and **no AI attribution lines** (project commit policy).
   - Run `make test` before every commit; the existing tests (249 unit + 9 data checks) must stay green.
7. **Honesty.**
   - Report every metric next to its baseline, on validation and (finally) test, with n.
   - Never tune on test.
   - If a gate fails, say so plainly, keep the baseline, and do not lower the gate.

---

## M0. Setup and data inspection (do first)

1. Run the engine calibration (engine-v3) so the ML work builds on calibrated baselines:
   ```bash
   git checkout feature/engine-improvements && git pull
   make engine-cal && make elec-split
   .venv/bin/python tests/fixtures/hand_calc_demo.py && make test && make validate-sim && make score
   git add configs/ tests/fixtures/ && git commit -m "Engine calibration from York/NEED data" && git push
   git checkout -b feature/ml
   ```
2. Dependencies: add `requirements.txt` with pinned versions of what is installed: pandas, pyarrow, numpy, scipy, scikit-learn, lightgbm, optuna, shap, pydantic>=2.7, pytest, openpyxl, duckdb, rapidfuzz, odfpy, tabulate. Run `pip install -r requirements.txt`.
3. Write `pipelines/ml/inspect_data.py`. It prints **schema only** (column, dtype, null %, n distinct; no values from restricted columns) for:
   - `homes_tagged.parquet`
   - `epc_certs_all.parquet` (raw certificate columns + canonical `c_*` columns + `property_id`)
   - `retrofit_history.parquet` (`property_id, from_date, to_date, field, old, new`)
   - `sales_matched.parquet`
   - `need_4m.parquet` (or `need_50k.parquet`)
   - `benchmarks.parquet`

   Save the output to `docs/validation/ml_data_inventory.txt`. Confirm the assumptions in this plan, and adapt column names where they differ: record any difference in `docs/ML.md`.

**Done when:** the inventory is committed and requirements install cleanly.

---

## M1. Shared feature layer (one code path for training and inference)

`backend/app/ml/features.py`: pure functions, no I/O.

### M1.1 Canonical state
- `state_from_home(HomeRecord)` and `state_from_certificate(row)` both return the **same dict of HomeRecord field names**.
- Certificates use the `c_*` canonical columns and the raw description columns (`walls_description`, `roof_description`, `floor_description`, `main_fuel`, `mainheat_description`, `transaction_type`, `number_habitable_rooms`, `photo_supply`, `solar_water_heating_flag`, `wind_turbine_count`).
- This lets one feature function serve homes, historical certificates and sales.

### M1.2 Feature function
`features(state, purpose) -> dict`. `purpose` ∈ {`sap`, `value`, `energy_york`, `recommender`}.

**Ordered (as integers, so monotone constraints work):**
- walls / roof / floor / windows / heating ratings: Very Poor = 1 … Very Good = 5; N/A = 0 plus an `*_na` flag; missing = NaN plus an `*_missing` flag;
- glazing: single 0, partial 1, double 2, triple 3;
- `multi_glaze_pct`;
- controls: none 0, timer 1, full 2, smart 3;
- solar PV 0/1; `pv_roof_pct`;
- `loft_mm` (reuse `feasibility.loft_depth_mm`; 0 for "no insulation").

**Parsed from description text** (write small regex parsers with unit tests; reuse `feasibility.roof_type` and `feasibility._wall_type`):
- wall type: cavity, solid, timber, system, unknown;
- wall insulation: none, partial, filled cavity, internal, external, insulated (assumed), unknown;
- roof type; floor type: solid, suspended, dwelling below, unknown; floor insulated flag;
- main fuel: mains gas, electricity, oil, LPG, solid, other;
- heating system family: boiler, storage heaters, room heaters, heat pump, community, other.

**Fabric and size:**
- `log_floor_area`;
- `habitable_rooms`;
- `area_per_room`;
- `age_mid_year` (midpoint of age band; "before 1900" = 1890);
- `property_type` × `built_form` (categorical);
- `mains_gas`.

**Certificate context:**
- `lodgement_year`, to absorb RdSAP methodology changes 2008–2026. At inference, set it to the current year;
- `transaction_type` (categorical);
- `epc_age_years` (only where meaningful; never for value labels).

**Location (value and energy only):** `postcode_district` (outward code) and `postcode_sector` (outward + first inward digit), both categorical.

### M1.3 Feature contract
`FEATURE_SETS[purpose]` lists the exact columns. Write a test that asserts:
- (a) no `label_only` or `restricted_address` column feeds any set;
- (b) training and inference produce identical columns and dtypes for the same home;
- (c) categories are frozen from train and stored in `meta.json`; unseen categories map to missing.

**Tests:** parser tables (≥ 30 description strings with expected outputs), contract test, round-trip test (a home and its own latest certificate give identical features).

---

## M2. EPC SAP model: predicts the EPC score of a home state (post-retrofit EPC)

**Why:** the after-retrofit Green Home Score currently keeps the EPC part "unchanged, EPC not re-assessed". The value model needs the SAP change of a scenario, and customers want "E → C".

### Data
- **Training rows:** every certificate of **train-split homes** in `epc_certs_all` (not only the latest), with features from `state_from_certificate`. Target = `c_sap_score`.
- **Weights:** the latest certificate per home counts 1.0; older ones 0.5, so homes with many certificates don't dominate.
- **Validation and test:** latest certificate of val / test homes.
- **Drop:** SAP missing or outside 1–110; floor area implausible.

### Models
| Model | Description |
|---|---|
| B0 | Median SAP by `property_type` × `age_band` (train) |
| B1 | Ridge on one-hot / ordinal features |
| **M** | **LightGBM regression with monotone constraints (+1)** on every ordered "better state" feature: the five ratings, glazing, `multi_glaze_pct`, controls, solar PV, `loft_mm`, wall insulation level, floor insulated. No constraint on heating family or fuel: a heat pump can lower SAP on electricity prices. |

### Tuning
- Optuna TPE, 60 trials, 5-fold `GroupKFold(property_id)` on train, early stopping (200 rounds patience).
- Search: `num_leaves` 15–255, `learning_rate` 0.02–0.1, `min_data_in_leaf` 20–300, `feature_fraction` 0.5–1, `bagging_fraction` 0.6–1 (`bagging_freq` 1), `lambda_l2` 0–10.
- Refit on all train rows with `n_estimators` = mean best iteration × 1.1.

### Metrics (val; test only at M7)
- MAE, RMSE, R²;
- % of homes within ±3 and ±5 SAP;
- EPC band exact and within-one-band accuracy;
- error by property type, age band, EPC band.

### Counterfactual validation (the key test for this model)
Build `pipelines/ml/build_epc_pairs.py`: consecutive certificate pairs of the **same home** where:
- (a) property type, built form and age band are unchanged;
- (b) floor area changed by < 5%;
- (c) at least one element changed (the `retrofit_history` fields, or loft mm, wall insulation, glazing, heating, controls, PV).

Use pairs from **val/test homes only**. Predicted ΔSAP = M(new state) − M(old state), with `lodgement_year` held at the new certificate's year in both, to remove methodology drift. Compare with the observed ΔSAP:
- MAE of Δ, Pearson r, sign agreement;
- mean bias by measure type (loft, walls, glazing, heating, controls, PV);
- baseline Δ0 = mean observed Δ per measure type from **train** pairs.

### Gates
- Val MAE < B0 and < B1.
- Monotonicity test: on 10,000 random homes × each upgrade (`apply_state_effects`), predicted ΔSAP ≥ 0 for fabric, glazing, controls and PV. Guaranteed by the constraints; the test proves it.
- Counterfactual ΔSAP MAE < Δ0 baseline MAE.
- Sanity: SAP is computed from these same elements, so expect high R². If val R² < 0.75, investigate the feature parsing before tuning further.

### Integration
`backend/app/services/sap_model.py`:
- `predict_sap(state)`;
- `sap_change(home, measures)` = predict(after state from `score.apply_state_effects`) − predict(before).

Changes to `score.score_after`:
- the energy-efficiency part becomes `clip(observed SAP + ΔSAP, 1, 100)` with status `modelled_epc_change` and provenance `modelled`;
- if the model is absent, keep today's behaviour;
- add `rating_after_indicative`.

**Artifacts:** `models/sap/model.txt`, `meta.json`, `docs/validation/ml_sap.json`, `docs/validation/ml_sap_pairs.json`.

---

## M3. Property value model (indicative uplift range)

**Gate status:** `configs/value_gate.json` = audited, precision 1.00 (95% CI 0.929–1.000), 4,000 matched sales. Condition 3, the coverage check, is evaluated here.

### Data
- `sales_matched` rows with `match_status == "linked"`, `epc_rating_at_sale_status == "observed"`, category A sales.
- Features from the **at-sale certificate**: join `epc_cert_at_sale` → `epc_certs_all.certificate_number` → `state_from_certificate` (purpose `value`).
- Sale fields: `new_build`, `tenure` (F/L), Land Registry `property_type` (D/S/T/F), sale month index (months since 2025-01), `postcode_district`, `postcode_sector`.
- Target: `log(price)`.
- Splits: the existing home split (sales inherit it). Also report a **time split** (train ≤ 2025-12, evaluate 2026) as a robustness check.

### Models
| Model | Description |
|---|---|
| B0 | Median price per postcode sector × LR type, falling back to district × type, then district |
| B1 | Hedonic ridge on log price. One-hot district, type, built form, age band and tenure; linear `log_floor_area`, `habitable_rooms`, month, **SAP at sale**. Interpretable "% per SAP point". |
| **M** | **LightGBM** on all value features. Location via out-of-fold smoothed target encoding (computed inside CV folds only) plus district categorical. Monotone +1 on `log_floor_area` only. No constraint on SAP: the data must show it. |

**Tuning:** as in M2, but 40 trials, GroupKFold on `property_id`. Also report a GroupKFold on postcode sector (spatial generalisation) for information.

**Metrics (val):**
- **MdAPE** (median absolute % error, the standard automated-valuation measure);
- PPE10 and PPE20 (share of homes within ±10% / ±20%);
- R² on log price; bias (median % error);
- each by type and district.

### Uplift for a scenario
`ΔSAP = sap_change(home, measures)` (M2). Then:
- **Hedonic route:** uplift % = exp(β_SAP × ΔSAP) − 1. Take β from **500 bootstrap resamples clustered by postcode sector** (p10 / p50 / p90).
- **GBM route:** predict the home at observed SAP and at SAP + ΔSAP, with all other features fixed (the "same property before and after" comparison the brief asks for), averaged over the 5 CV models.
- **Reported range:**
  - low = min(hedonic p10, GBM);
  - high = max(hedonic p90, GBM);
  - mid = hedonic p50.

  It is always labelled *"estimated potential property-value impact based on historical and market relationships in the dataset prepared by the team"*, with the caveats: association, not causal; condition and micro-location confounding; 20 months of sales.

**Current value estimate:** GBM prediction at the latest month, with a **split-conformal 80% interval** (absolute log residual quantiles on val). Report coverage on test at M7. This is the D10 coverage check: **pass if 0.75 ≤ empirical coverage ≤ 0.85**; write the result to `configs/value_gate.json` (`coverage_check`).

**Gates:**
- M val MdAPE < B0 val MdAPE.
- Hedonic β_SAP bootstrap interval reported, whatever its sign.
- Coverage check passes, or the valuation stays gated with the reason shown.

### Integration
`backend/app/services/valuation.py` replaces `scenario_builder.valuation()`. Extend the `Valuation` schema (keep existing fields):
- `low_pct`, `mid_pct`, `high_pct` (validator: low ≤ mid ≤ high when ok);
- `sap_before`, `sap_change`, `sap_after_indicative`, `rating_before`, `rating_after_indicative`;
- `current_value_gbp`, `current_value_low_gbp`, `current_value_high_gbp`;
- `potential_value_low_gbp`, `potential_value_high_gbp`;
- `measures`, `provenance = modelled`, `basis`, `caveats`, `model_versions`.

The service abstains (`not_estimated` plus reason) when:
- the gate is closed;
- a model is missing;
- there are no measures;
- the SAP score is missing;
- the district is unseen (value £ only; % may still be given).

The existing test `test_valuation_gated` must be updated to the new reasons. Add tests for each abstain reason.

**Artifacts:** `models/value_gbm/model.txt`, `models/value_hedonic.json` (coefficients plus bootstrap β quantiles), `docs/validation/ml_value.json`.

---

## M4. Energy consumption model (NEED): candidate replacement for the cell-median benchmark

### Data
- `need_4m.parquet` (fall back to `need_50k`), using its own `split`.
- Gas target: `gas_status == "metered"`, `main_heat_gas == 1`, `gas_kwh > 0`.
- Electricity target: `elec_status == "metered"`, `elec_kwh > 0`.
- Features: **only those also available for York homes**: property type, age band code, floor-area band code (or representative area), region code, EPC band, main heat gas, solar PV.

  NEED-only fields (council tax band, IMD, insulation scheme flags) must **not** be used, because York homes don't have them. Document this choice.

### Models
| Model | Description |
|---|---|
| **B0** | The engine's benchmark: median per main fuel × type × EPC band × area band, with the L1 → L2 → L3 fallback and ≥ 30 homes, recomputed on **train only**, plus the D21 area scaling. This is the bar to beat. |
| **M** | LightGBM on log kWh (try l2 and huber; pick on val) |
| **Q** | LightGBM quantile models (α = 0.1, 0.5, 0.9), giving a per-home P10–P90 to replace the lognormal spread in the Monte Carlo (D28) |

- Tuning: 40 trials on a stratified 500k-row train subsample, then refit on the full train split.
- Metrics (val):
  - MAE and MdAPE in kWh;
  - R² on log kWh;
  - for Q: interval coverage of P10–P90 (target ~0.80) and pinball loss;
  - all overall and on the **Yorkshire and The Humber** subset (`region_code == "E12000003"`).

**Gate:** M beats B0 MAE by ≥ 2% overall **and** is not worse on the Yorkshire subset. Write `configs/model_switch.json`:
```json
{"use_model_baseline": <gate>, "beat_benchmark": <gate>, "model_version": "...", "val_mae": {...}, "benchmark_val_mae": {...}}
```

### Integration
- `pipelines/ml/predict_energy_york.py`: map York homes to NEED features (`units.need_keys`, age band → code, area → band) and write `modelled_energy.parquet` (`property_id`, gas / elec P10, P50, P90). Gas only for gas-heated homes; an observed 0 stays 0.
- `baseline.get_baseline(..., use_model=True)` uses P50 when the switch is on (provenance `modelled`).
- Add `ScenarioRequest.use_model_baseline: bool = False`.
- The Monte Carlo uses Q intervals when available.
- **Be honest:** the features are banded, so expect a modest gain over cell medians. The main value is smoothing sparse cells and providing quantiles. If the gate fails, ship B0 and the quantile models only, and report both.

**Artifacts:** `models/energy_gas/`, `models/energy_elec/`, `models/energy_q*/`, `docs/validation/ml_energy.json`.

---

## M5. Retrofit recommender (relevance ranking of feasible measures)

**Labels:** `rec_loft_insulation`, `rec_cavity_wall`, `rec_solid_wall`, `rec_double_glazing`, `rec_smart_thermostat`, `rec_heat_pump`, `rec_solar_pv`. These are what the accredited assessor's software suggested on the latest certificate (`docs/LABELS.md` §2). Agreement with them means *"consistent with the EPC assessor"*, not *"feasible"*: say this in every report.

### Data
- Latest certificate state of every home (homes_tagged plus the M1 features, purpose `recommender`).
- Train / val / test by the home split.
- Per measure, **train and evaluate only on homes where the engine rule is not infeasible** (`feasibility.assess`). ML may only reorder feasible measures.

### Models
| Model | Description |
|---|---|
| B0 | Rules only: every feasible measure scores 1 (precision / recall of "feasible ⇒ recommended") |
| B1 | Prevalence of `rec_m` by property type × age band (train) |
| B2 | The engine's order: suitability High > Medium > Low, then catalogue order |
| **M** | One LightGBM binary classifier per measure (`is_unbalance` or `scale_pos_weight`), tuned with 30 trials each on GroupKFold, then **isotonic calibration on val folds** (out-of-fold on train, applied to val) |

`rec_heat_pump` has about 31 positives: do not train a model; report "insufficient labels" and keep the rules for it.

### Metrics (val)
- Per measure: ROC-AUC, PR-AUC, Brier, F1 at the threshold that maximises F1 on train out-of-fold predictions.
- **Ranking per home** over its feasible measures: NDCG@3, Precision@1, MAP. M is compared with B0 (random tie order), B1 and B2.
- Calibration plot data (10 bins) for each measure.

**Gate:** M beats B2 on NDCG@3 (val) and each shipped classifier beats B1 on PR-AUC. Measures that fail fall back to B2.

### Integration
- `pipelines/ml/score_recommender_york.py` writes `recommender_scores.parquet` (`property_id`, `p_<measure>`).
- `backend/app/services/recommender.py` → `ScenarioResult.recommendation_ranking`, an optional list of `{measure, assessor_relevance_prob, suitability, carbon_per_pound_kg, bill_saving_gbp, rank}`.
- **Priority order:** relevance probability (calibrated), ties broken by carbon per £ net.
- **Install sequence:** the engine's fixed physical order (fabric → glazing → controls → heat pump → PV), shown separately as "do in this order". The brief requires the order to reflect interactions.
- Infeasible measures never appear; `needs_verification` measures appear with a "verify" flag.

**Artifacts:** `models/rec_<measure>/`, `docs/validation/ml_recommender.json`.

---

## M6. Explainability and responsible-AI inputs
- **SHAP:** `TreeExplainer` for M2 and M3. Save global mean |SHAP| (top 15) to `docs/validation/ml_shap_<model>.json`, and expose per-home top-5 contributions through the services (`explain=True`), for the LLM layer later.
- **Slice metrics** (val, then test at M7) by property type, age band, EPC band, tenure (value), built form and postcode district. Flag any slice whose error is more than 1.5× the overall error. Save to `docs/validation/ml_slices.json`.
- **Model cards:** one section per model in `docs/ML.md`: purpose, data, features, label definition and limits, metrics vs baselines, slices, known failure modes, intended use, version.

---

## M7. Final held-out evaluation, test predictions and report (run once)
1. `pipelines/ml/evaluate_models.py` loads the frozen models and scores **test** once: every metric above, against the same baselines, with n. It writes `docs/validation/ml_test.json`.
2. Value coverage check on test → `configs/value_gate.json` `coverage_check` (pass / fail plus numbers). The value status becomes `enabled` only if every condition passes.
3. `pipelines/ml/write_test_predictions.py` writes `eval/test_predictions.csv`, one row per **test** home (scenario "baseline" and "all feasible"), following the schema in `docs/DATA.md` §5:
   - score and sub-scores;
   - baseline and predicted gas / elec;
   - after-retrofit energy and savings per fuel;
   - improvement potential;
   - CO₂e;
   - recommended measures (priority order);
   - value uplift low / mid / high;
   - `prediction_status`;
   - `model_version`.

   No addresses or full postcodes.
4. `docs/EVALUATION.md`: one table per model (baseline vs model, val and test), counterfactual SAP pairs, value coverage, slices, what failed its gate and what ships. Plain language; every number traceable to a JSON file.
5. Update `docs/PROGRESS.md`, `docs/DECISIONS.md` (new decisions D30+ for each modelling choice), `README` run instructions and the `Makefile`:
   ```make
   ml-data:     build features, EPC pairs
   ml-train:    train + tune all models (val only)
   ml-predict:  York predictions (energy, recommender)
   ml-eval:     test once + test_predictions.csv + EVALUATION.md
   ml:          all of the above
   ```

---

## File layout to create
```
backend/app/ml/__init__.py, features.py, parsers.py, splits.py, metrics.py, tuning.py, registry.py
backend/app/services/sap_model.py, valuation.py, energy_model.py, recommender.py
pipelines/ml/inspect_data.py, build_feature_tables.py, build_epc_pairs.py,
             train_sap_model.py, train_value_model.py, train_energy_model.py, train_recommender.py,
             predict_energy_york.py, score_recommender_york.py, evaluate_models.py, write_test_predictions.py
models/<name>/model.txt + meta.json            (committed)
configs/model_registry.json                    (versions, gates, headline metrics; read by config.versions())
configs/model_switch.json, configs/value_gate.json (updated)
docs/ML.md, docs/EVALUATION.md, docs/validation/ml_*.json
eval/test_predictions.csv
tests/unit/test_ml_features.py, test_ml_parsers.py, test_ml_metrics.py, test_ml_sap.py, test_ml_value.py,
           test_ml_energy.py, test_ml_recommender.py, test_ml_integration.py
```

`registry.py` loads `models/<name>/meta.json` and `model.txt` lazily (`lru_cache`). It returns `None` when absent, and every service then abstains with a reason. Unit tests must pass **without** the trained models: train tiny models on synthetic data inside the tests.

## Test requirements (minimum)
- **Parsers:** ≥ 30 real-style description strings.
- **Leakage:** the feature-contract test; a value-model test that fails if any latest-certificate field is used.
- **Monotonicity:** the SAP model, on synthetic plus (if present) real homes.
- **Determinism:** same input, same prediction; scenario id changes when a model version changes.
- **Abstain paths:** every service, with each reason.
- **Integration:** `build()` with all models present (tiny synthetic models) and with none present. The demo A, B and C fixtures still pass.
- **Metrics:** NDCG, MdAPE, PPE10, pinball loss and coverage functions against hand-computed values.

## Order and expected effort
| Milestone | Effort | Depends on |
|---|---|---|
| M0 setup + inventory | 0.5 h | — |
| M1 features + parsers | 2–3 h | M0 |
| M2 SAP model + pairs | 3–4 h | M1 |
| M3 value model + valuation service | 3–4 h | M2 |
| M4 energy model | 2–3 h | M0 |
| M5 recommender | 2–3 h | M1 |
| M6 SHAP, slices, model cards | 1–2 h | M2–M5 |
| M7 test once + predictions + report | 1–2 h | all |

If time is short, keep this priority: **M1 → M2 → M3 → M5 → M7 → M4 → M6**. M2 and M3 unlock the value range and the "E → C" story; M5 is the recommendation-quality evidence.

## Report back after each milestone (paste into the chat with the planning assistant)
- Metrics table (val), model vs baselines, with n.
- Gate pass / fail.
- Anything in the data that differed from this plan.
- `git log --oneline -3`.
- **No addresses, postcodes beyond outward code, or raw rows.**
