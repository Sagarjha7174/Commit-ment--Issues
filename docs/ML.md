# ML phase (Phase D): data notes, deviations and model cards

Decisions: `docs/DECISIONS.md` D30+. Metrics: `docs/validation/ml_*.json`.
Work is local only (branch `feature/ml`, created from `feature/engine-core`; the engine code is identical to the
`feature/engine-improvements` snapshot the plan was written against).

## 1. Data inventory (M0)
Schema-only inventory: `docs/validation/ml_data_inventory.txt` (`pipelines/ml/inspect_data.py`, `make ml-inspect`).
Address columns are listed by name and never loaded (D31).

| Table | Rows | Notes |
|---|---|---|
| homes_tagged | 65,872 | split train 46,151 / val 9,797 / test 9,924 |
| epc_certs_all | 95,348 | train-home certificates 66,631; val 14,132; test 14,585 |
| retrofit_history | 32,051 | fields: roof_rating, walls_rating, controls, glazing, heating_type, solar_pv |
| sales_matched | 4,095 | linked 4,000; at-sale rating observed 3,996; split train 2,794 / val 587 / test 619 |
| need_4m | 4,000,000 | split train 2.80M / val 0.60M / test 0.60M; Yorkshire and The Humber 369,297 |

## 2. Differences from the plan (adapted)
1. **`epc_certs_all` has no `split`.** Certificates inherit their home's split by joining `homes_tagged` on `property_id`.
2. **No outward code / sector column in `homes_tagged` or `epc_certs_all`.** Derived from `postcode` inside `safe_read_parquet(derive_postcode=True)`, which drops the postcode immediately. York has 11 outward codes and 40 sectors.
3. **`retrofit_history` fields** are only roof_rating, walls_rating, controls, glazing, heating_type and solar_pv. Loft depth and wall-insulation changes (needed for the M2 counterfactual pairs) are taken from the two certificates' descriptions instead.
4. **Sales `property_type`** is a label (Detached / Semi-detached / Terraced / Flat/Maisonette), not the D/S/T/F code; used as is.
5. **No PPD category column** in `sales_matched`; `ppd.parquet` already keeps category A only (DATA.md 1.4), so every row is category A.
6. **Habitable rooms** exist only as the raw certificate column `number_habitable_rooms` (no canonical `c_*` column).
7. **NEED columns:** `property_type`, `age_band_code`, `floor_area_band_code`, `floor_area_m2_rep`, `region_code`, `epc_band`, `main_heat_gas`, `solar_pv` (no `need_` prefix).
8. **Certificates per home** go up to 67 (shared UPRNs / blocks); the M2 weights (latest 1.0, older 0.5) are kept, see M2.
9. **Engine calibration not applied** (D30); 4 tests already fail on the unmodified branch (D30).

## 3. Feature layer (M1)
`backend/app/ml/features.py` (ml-features-v1), `parsers.py`, `metrics.py`, `splits.py`. Purposes and columns: `FEATURE_SETS`;
sources: `FEATURE_SOURCES` (tested against `configs/feature_availability.json`). Decisions D32, D33.

| Purpose | Columns | Notes |
|---|---|---|
| sap | 40 | element ratings (ordinal, N/A = 0 + flag, missing = NaN + flag), glazing, controls, PV, loft mm, wall/floor insulation level, U-values, types, fuel, heating family, size, age, type x form, mains gas, lodgement year, transaction type; no SAP / band |
| value | 18 + 4 sale fields | SAP at sale, size, age, type, construction, heating, location (outward code, sector) |
| energy_york | 7 | NEED-coded: type, age band, area band, EPC band, gas heating, PV, region |
| recommender | 42 | sap set + SAP score and band of the certificate |

Parse coverage over all 95,348 certificates: wall type unknown 9.2% (U-value or code only), roof type unknown 6.5%,
floor type unknown 6.4%, loft depth missing 30.3% (no depth recorded, flats with a dwelling above).

## 4. Model cards
Numbers (val and test, with n, against baselines) are in `docs/EVALUATION.md`, generated from `docs/validation/ml_*.json`.
Versions: `configs/model_registry.json` (a model is loaded only if `shipped`). Seed 42; deterministic LightGBM
(`deterministic`, `force_row_wise`, 8 threads); Optuna TPE seeded, sequential trials.

### 4.1 EPC SAP model (`models/sap`, M2)
- **Purpose:** the SAP score of a recorded home state, so a retrofit's EPC change (ΔSAP = after − before, same lodgement year) can be shown ("E → C", indicative) and fed to the value model.
- **Data:** every certificate of train homes (95k certificates in York; latest weight 1.0, older 0.5); val/test = latest certificate of val/test homes. SAP outside 1–110 or implausible floor area dropped.
- **Features:** `FEATURE_SETS["sap"]` (40): element ratings, glazing, controls, PV, loft depth, insulation levels, U-values, construction types, fuel, heating family, size, age, type × form, lodgement year, transaction type. Monotone +1 on every "better state" input, −1 on U-values; heating family and fuel unconstrained.
- **Label:** `c_sap_score` as lodged (RdSAP/SAP methodology changes over 2008–2026 absorbed by lodgement year).
- **Checks:** MAE vs B0 (median type × age) and B1 (ridge); counterfactual pairs of the same home vs the Δ0 baseline; monotonicity on 10,000 homes; R² sanity.
- **Known failure modes:** a heat pump's modelled ΔSAP depends on the after-state the engine builds. Keeping the old heating rating had modelled electric homes as "heat pump rated Very Poor" (ΔSAP +0.5, 39% negative); since D46 the after-state takes the heating rating and controls of York heat-pump certificates (electric homes +12.4, none negative; observed storage heaters → heat pump pairs +11.8). On real after-certificates the model matches observed changes (gas boiler → heat pump pairs: train +7.4 vs +6.7 observed, test +7.6 vs +9.8). For gas-heated homes a heat pump alone still gives a small modelled fall (median −2.9), consistent with SAP's cost basis; only 10 pure gas → heat pump swaps exist, too few to calibrate (`docs/FAILURE_ANALYSIS.md` §4); new-build U-value-only descriptions are coarse; a measure whose state was not recorded (missing rating, unknown loft depth) gets no credit for that input (never turned from missing into known).
- **Slices (val, `ml_slices.json`):** error is highest at the band extremes: EPC F (MAE 10.4, n 121), G (8.9, n 42), E (6.8, n 829) and A (5.8, n 84) vs 3.5 overall. Treat indicative "after" bands for F/G homes with extra caution.
- **Explanations:** top drivers (mean |SHAP|, `ml_shap_sap.json`): heating rating, wall rating, type × form, wall and floor insulation level, age; `sap_change(explain=True)` returns the top-5 inputs behind a home's ΔSAP.
- **Intended use:** indicative EPC change for a scenario, shown next to the score (D34). Not an EPC assessment.

### 4.2 Property value models (`models/value_gbm`, `models/value_hedonic.json`, M3)
- **Purpose:** an indicative range for the property-value impact of a scenario's EPC change, and a current-value estimate with an 80% interval.
- **Data:** York Land Registry sales 2025-01..2026-08 linked to an EPC home with an observed at-sale certificate (audited match precision 1.00, D10); features from the **at-sale** certificate; sales inherit the home split.
- **Features:** SAP at sale, size, rooms, age, type, construction, heating, glazing, PV, Land Registry type, tenure, new build, sale month, outward code, sector target encoding (out-of-fold on train). Element ratings excluded (D33). Monotone +1 on floor area only.
- **Models:** GBM (log price) and hedonic OLS (β_SAP with a 500-resample bootstrap clustered by postcode sector). Uplift range = min/max of the hedonic p10/p90 and the GBM "same home at SAP and SAP + ΔSAP" (5 CV models), mid = hedonic p50.
- **Gate:** GBM val MdAPE < B0; the value status is `enabled` only if the D10 coverage check passes on test (0.75–0.85 for the 80% split-conformal interval), see `configs/value_gate.json`.
- **Slices:** flats and maisonettes have MdAPE 15.0% (n 84) vs 9.0% overall (flagged > 1.5x). Drivers (`ml_shap_value.json`): floor area dominates, then rooms, outward code, sector encoding, tenure.
- **Limits:** association, not causal; condition and micro-location unobserved; 20 months of one city; homes never sold use assumed sale fields (D35); an unseen outward code drops the GBP value.

### 4.3 Energy models on NEED (`models/energy_*`, M4)
- **Purpose:** candidate replacement for the cell-median benchmark baseline, and per-home P10–P90 for the Monte Carlo.
- **Data:** NEED 4M sample, rows with an EPC band, its own split; gas = metered gas of gas-heated homes, electricity = metered import.
- **Features:** only those York homes share with NEED (type, age band, floor-area band, EPC band, gas heating, PV, region); NEED-only fields excluded.
- **Gate:** ≥ 2% MAE gain over B0 overall and not worse on Yorkshire, per fuel; the switch needs both (D36). Quantile models ship if their pinball loss beats the cells' own quantiles.
- **Limits:** banded inputs, so the gain over cell medians is small; NEED cannot be linked to York homes, so York accuracy is unmeasured.

### 4.4 Retrofit relevance classifiers (`models/rec_*`, M5)
- **Purpose:** order a home's feasible measures by how likely an EPC assessor would recommend them (calibrated probability), ties by carbon per pound; install order stays the engine's physical order.
- **Data:** latest certificate state of York homes; per measure only homes where the engine rule is not infeasible.
- **Labels:** `rec_*` (assessor software suggestions, label_only); heat pump has too few labels (rules only, D37).
- **Gate:** each classifier's PR-AUC > B1 (prevalence by type × age); the ranking's NDCG@3 > B2 (engine order).
- **Limits:** agreement means "consistent with the EPC assessor", not feasibility or value for money; assessor rules depend on the same fields, so high scores are expected.
