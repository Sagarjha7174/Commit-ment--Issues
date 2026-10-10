# Green Home Score

Code: `backend/app/services/score.py`. Mappings: `configs/score_mappings.json` (score-map-v1). Intensity percentiles:
`configs/score_params.json` (score-params-v1, train split, never recomputed). After-retrofit state changes:
`configs/retrofit_state_effects.json` (state-effects-v1). Batch scoring: `pipelines/score_homes.py` → `homes_scored.parquet`.

## 1. Formula
S = Σ wₖ·sₖ, sₖ ∈ [0, 100], fixed weights (Σ = 1), total rounded half-up to an integer.

| Part | Weight | Input | Mapping |
|---|---|---|---|
| Energy efficiency | 0.25 | EPC SAP score | `min(max(SAP, 0), 100)` |
| Energy intensity | 0.20 | x = (baseline gas + baseline elec) / floor area, kWh/m²/yr | `100·(p90 − x)/(p90 − p10)`, clipped 0–100; p10 = 75.749, p90 = 186.022 |
| Insulation | 0.15 | EPC walls / roof / floor ratings | ratings → points (below); weights 0.5 / 0.35 / 0.15 over the elements that apply, renormalised |
| Heating | 0.15 | EPC main-heating rating, heating type | ratings → points; heat pump ≥ 75 |
| Windows | 0.10 | glazing, % multi-glazed | single 10, double 75, triple 100; partial = 10 + 65·pct/100 (pct missing → 50%, assumption) |
| Renewables | 0.10 | solar PV, PV roof %, solar thermal, wind | none 0; PV 60; PV ≥ 50% of roof 100; +30 solar thermal; +30 wind; cap 100 |
| Smart controls | 0.05 | controls category | none 0, timer 40, full 70, smart 100 |

Rating points: Very Poor 10, Poor 30, Average 55, Good 80, Very Good 100.

Classes: 80–100 Highly efficient, 65–79 Good, 50–64 Moderate, 30–49 Poor, 0–29 Very poor (on the rounded total).

## 2. Why each mapping is monotonic
Every mapping is a non-decreasing function of an ordered state. SAP and the clipped intensity line are monotonic by construction. The rating points rise strictly from Very Poor to Very Good. Partial glazing rises linearly between single and double. Renewables only add points. The heat-pump floor is a `max()`, so it can only raise a sub-score. The tests in `tests/unit/test_score.py` check every mapping across its whole range.

## 3. Avoiding double counting
- **Energy efficiency** uses the recorded EPC rating measure (SAP).
- **Energy intensity** uses annualised purchased energy per m² (the NEED benchmark baseline, or a user reading when one is supplied), never the EPC modelled-energy columns. The deprecated `epc_predicted_consumption_kwh_m2_primary` is never read.
- **Known overlap:** the benchmark cells are keyed partly by EPC band (D2, D6), so intensity is correlated with the efficiency part. We keep it because the brief asks for an intensity part and no metered York data exists (D6). A customer's own meter reading replaces the benchmark and removes the overlap.
- **Element ratings:** heating and insulation also use EPC element ratings, which feed SAP. They are kept separate because the brief defines them as their own parts, and they tell the customer which element is weak (justification required by section 2 of the brief).

## 4. Missing data
- Weights never change.
- A missing part is scored **50** for the headline, and **0 / 100** for `range_low` / `range_high`.
- `completeness` = k/7, and `missing_parts` lists the gaps.
- More than 2 missing parts → `status = unavailable` and `total = null`. Never a silent 0.
- `not_applicable` elements, such as a roof with another dwelling above, are skipped inside the insulation part. They are not treated as missing.
- If no element applies at all, the insulation part is missing.

Intensity is missing when:
- the gas or electricity baseline is unavailable,
- the floor area is missing or implausible, or
- a gas boiler is recorded but there is no mains gas (conflict flag).

An observed 0 kWh gas baseline for a home without mains gas is a real value, not a missing one.

## 5. Output per part
`sub`, `used_sub`, `weight`, `points = weight × used_sub`, `provenance`, `status`, `detail`. The validator checks that the points sum to `raw_total`. Key issues = parts whose sub-score is below 50.

## 6. After-retrofit score
Only the parts whose inputs change are recomputed (`retrofit_state_effects.json`):

| Measure | Part | Effect (at least, never a downgrade) |
|---|---|---|
| loft insulation | insulation | roof → Good |
| cavity / solid wall | insulation | walls → Good |
| double glazing | windows | double, 100% |
| smart thermostat | smart controls | smart |
| heat pump | heating | type = heat pump (heat-pump floor 75 applies) |
| solar PV | renewables | PV of unknown size → 60 |
| any | energy intensity | recomputed from the simulated after-energy (grid import + gas) |

- The **EPC SAP score is not re-assessed**, so energy efficiency stays the same and is labelled `unchanged_epc_not_reassessed`.
- A missing state stays missing after a retrofit, so a retrofit never turns "unknown" into points.
- The score is never forced upward. Carbon is reported separately.

## 7. Hand-checked example: demo home A (1967–75 detached house, EPC E)
| Part | Calculation | Sub | Points |
|---|---|---|---|
| Energy efficiency | SAP 48 | 48.000 | 12.000 |
| Energy intensity | (21,616.67 + 3,766.67)/171 = 148.44 → 100·(186.022 − 148.44)/110.273 | 34.080 | 6.816 |
| Insulation | walls Poor 30 × 0.5 + roof Very Poor 10 × 0.35, ÷ 0.85 (floor N/A) | 21.765 | 3.265 |
| Heating | gas boiler, Good | 80.000 | 12.000 |
| Windows | partial, 87%: 10 + 65 × 0.87 | 66.550 | 6.655 |
| Renewables | none | 0.000 | 0.000 |
| Smart controls | full | 70.000 | 3.500 |
| **Total** | | | **44.236 → 44, Poor** |

## 8. Distribution (train split, 46,151 homes, score-map-v1)
| Class | Homes | Share |
|---|---|---|
| Highly efficient | 1,754 | 3.8% |
| Good | 7,925 | 17.2% |
| Moderate | 27,500 | 59.6% |
| Poor | 8,786 | 19.0% |
| Very poor | 149 | 0.3% |
| unavailable | 37 | 0.1% |

Mean score by EPC band: A 79.6, B 75.1, C 61.1, D 53.1, E 45.9, F 40.7, G 30.5. The order is monotonic.

Completeness: 39,694 homes have 7/7. The most common missing parts are renewables (5,735, PV not recorded on older EPCs) and intensity (3,080, gas baseline unavailable).
