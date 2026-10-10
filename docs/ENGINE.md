# Engine: baseline, feasibility, simulator, carbon, packages (engine-v2)

Code: `backend/app/services/`. Plain deterministic Python, with Pydantic v2 schemas in `backend/app/schemas/`. Every number is produced here; the LLM layer only explains these outputs.

## 1. Accounting contract
- All energy is in **kWh/year**, and carbon is in **kg CO₂e/year**.
- **Saving = before − after.** Positive means a reduction; an increase is a **negative** saving.
- Positive carbon means emissions fell.
- **Purchased energy** = gas + grid electricity import. Solar PV reduces grid import, not demand.
- **Missing values** are `null` with a status (`unavailable`, `not_estimated`, `blocked`), never 0.
- Every value carries provenance: `observed`, `population_benchmark`, `user_provided`, `modelled`, `assumption`, `derived`, `unavailable`, `not_applicable`.
- **Reconciliation** is asserted inside `simulate()` and again by the `SimResult` validator:
  - for each fuel, the total change equals the sum of the logged steps;
  - cooking gas never changes;
  - carbon parts sum to the total.

## 2. Baseline (`baseline.py`)
Priority order:
1. A **user reading** (`user_provided`), per fuel.
2. **Modelled energy**, used only if `use_model=True` *and* `configs/model_switch.json` says the model beat the benchmark. Default off.
3. The **NEED population benchmark** (D6).

**Blocking flags** (gas boiler without mains gas, zero or negative EPC energy, no heating description) make improvement potential `unavailable`. `gas_heated` = gas boiler, gas > 0 and no conflict.

## 3. Feasibility (`feasibility.py`)
- **States:** `feasible`, `infeasible`, `needs_verification`.
- **Missing input:** a missing critical input gives `needs_verification`, with `missing_inputs` listed; never `infeasible`.
- **Suitability:** High, Medium or Low, with a one-line reason.
- **ML:** may only reorder feasible measures, never override these rules.

| Measure | Infeasible when | Needs verification when |
|---|---|---|
| Loft | dwelling/premises above (flat not top floor); roof already Good or Very Good | roof N/A without "dwelling above", or roof rating missing |
| Cavity wall | walls Good or Very Good; solid or timber walls; cavity built 2000+ | wall type, wall rating or age missing (U-value-only descriptions) |
| Solid wall | walls Good or Very Good; cavity or timber walls | wall type or rating missing |
| Double glazing | already double or triple | glazing missing |
| Smart thermostat | already smart (TTZC proxy) | controls missing |
| Heat pump | already a heat pump | heating missing; gas-supply conflict |
| Solar PV | flat or maisonette; already has PV | property type or PV missing |

A flat gets heat-pump suitability Low, because outdoor space is unconfirmed. Electric-heated homes are feasible but get `not_estimated` impacts (§5).

## 4. Gas end-use decomposition (`units.py`)
- `gas_other = other_gas_share × gas` (0.0305; cooking, never touched)
- `gas_heat_water = gas − gas_other`
- `gas_space = space_share × gas_heat_water` (0.77); `gas_water = water_share × gas_heat_water` (0.23)
- `useful = gas × boiler_efficiency`: by EPC heating rating (Very Good 0.89, Good 0.85, Average 0.75, Poor 0.67, Very Poor 0.60; default 0.85), D18
- **Electrically heated homes** (D16): `elec_heat = share × elec`, where `share` comes from `configs/electric_heating_split.json`. `elec_space = 0.77 × elec_heat` and `elec_water = 0.23 × elec_heat`; the rest stays `elec_base`. Without the split file the engine abstains, as before (D13).
- All constants come from `configs/retrofit_catalogue.json` (cat-v3) and can be overridden per scenario through `Assumptions`.

## 5. Impact basis conversion (critical)
| Basis | Used by | Conversion |
|---|---|---|
| `total_gas` | loft, cavity, solid wall (NEED) | `kwh = impact × current total gas`; `frac = min(kwh / current gas_space, 1)`; useful space heat × (1 − frac) |
| `space_heat_demand` | double glazing, smart thermostat (brief ranges) | useful space heat × (1 − impact); partial glazing scales impact by the single-glazed share |
| `total_grid_electricity` | solar PV (NEED) | `pv_offset += impact × (elec_base + hp_elec)` |
| anything else | n/a | `not_estimated`, `impact_basis_unsupported` |

- **Impact level:** the catalogue mid by default; low or high can be selected for sensitivity.
- **Segment-aware impacts** (D15): for loft, cavity, solid wall and PV, the impact is headline + Σ shrunk segment deviations (EPC band, age, type, region; empirical Bayes), floored at 0. `Assumptions.segment_impacts = False` gives the headline. Each step note shows both figures.
- **Electrically heated homes** (D16): `total_gas` impacts become `frac = min(impact / (0.77 × (1 − 0.0305)), 1)` of electric space heat. `space_heat_demand` impacts apply directly to electric space heat.
- **Other non-gas-heated homes** (oil, other), or electric homes without the split: `not_estimated` with reason `heating_not_on_gas` (D13).

## 6. Order semantics
- **Fixed order:** loft → cavity → solid wall → double glazing → smart thermostat → heat pump → solar PV. The order in the request is ignored.
- Each step acts on the state left by the previous step, so reductions **multiply**: 15% then 20% = 32%, never 35%.
- The fabric total does not depend on the order among fabric measures: G·(a + b − ab) is symmetric.
- Removing a measure removes exactly its marginal row.

## 7. Heat pump
- **full:** removes space and water gas (cooking gas stays). `hp_elec = useful replaced heat / SCOP` (3.0; range 2.5–3.5).
- **partial:** replaces a declared share; the rest stays on gas.
- **unknown:** the engine abstains (`not_estimated`, `heat_pump_mode_unknown`).
- Electricity rises, which shows as a negative electricity saving.
- **Electric to heat pump** (D16): replaces electric space + water heat (efficiency 1.0) with `heat / SCOP`, an electricity saving of `heat × (1 − 1/SCOP)`. Without the split file it is `not_estimated` (`no_gas_to_displace`).

## 8. Solar PV
- Applied last, on grid electricity including any heat-pump electricity.
- Gas is never changed. Exports are not credited.

## 9. Improvement potential
- `100 × (purchased_before − purchased_after) / purchased_before` for the selected package.
- It is `unavailable` if the baseline is missing, zero or blocked.

## 10. Carbon (`carbon.py`)
- ΔC = ΔE_gas × 0.18231 + ΔE_elec × 0.14395 kg CO₂e/kWh (DESNZ 2026; electricity includes T&D losses, D5).
- Factors and their sources are echoed in every result.

## 11. Validation against NEED combination figures
- **Comparison:** `pipelines/validate_simulator.py` → `docs/validation/simulator_vs_need.json`.
  - Same basis (% of whole-home gas); tolerance ±5 pp vs the NEED median.
  - Only **combinations** are compared. Single-measure NEED figures are catalogue inputs, so comparing them would be circular.

| NEED combination | NEED median | Simulated | Gap |
|---|---|---|---|
| Cavity + loft | 8.38% | 14.81% | +6.43 pp (outside) |
| Solid wall + loft | 14.31% | 19.93% | +5.62 pp (outside) |
| Solid wall + heat controls | 9.15% | 21.58% | +12.43 pp (outside) |
| Solid wall + loft + heat controls | 10.27% | 24.04% | +13.76 pp (outside) |

- **Result:** the simulator **overestimates combined packages**.
- **Why it can't match:** NEED's cavity+loft median (8.4%) is lower than its cavity-alone median (12.0%). That points to different installation samples and in-use effects, which a multiplicative engineering model cannot reproduce.
- **Heat controls:** these map approximately to the smart thermostat, whose impact is the brief's range and is not validated.
- **Our response:** the engineering estimate is not tuned. Every multi-measure fabric/controls package carries a warning citing this gap (D14) **and** a NEED-calibrated reference figure (D17). The factors are solved so the reference home reproduces each NEED median exactly: 0.559, 0.712, 0.409 and 0.407, with a pooled 0.484 (`configs/combination_calibration.json`).

## 12. What the simulator does NOT model
- ventilation and infiltration
- thermal bridges
- weather and degree-days
- occupancy and behaviour, including rebound
- boiler replacement
- hot-water demand changes
- PV orientation, shading and export
- heat-pump sizing and flow temperature
- tariffs

It is a transparent accounting model, **not a digital twin**. Savings are estimates for a typical home of this type (benchmark baseline), not guarantees.

## 13. Packages (`packages.py`)
- **Enumeration:** every combination of feasible and needs_verification measures whose standalone impact can be estimated (at most 2⁷ = 128), including do-nothing (`none`).
  - `package_id` = the sorted measure ids joined by `+`.
  - Measures that can't be estimated are excluded, with a reason (`excluded_measures`).
- **Cost:** the catalogue mid cost (EPC indicative cost, provenance `assumption`). If a measure's cost is missing, the package stays in the list but is marked ineligible for cost comparison.
- **Confirmed vs conditional:** a package with only feasible measures is *confirmed*. Any needs_verification measure makes it *conditional*, and `must_verify` lists what to check.
- **Pareto filter:** cost lower, carbon saving higher, purchased saving higher. Confirmed packages are compared only with confirmed packages; conditional packages are compared with all packages.
- **Featured picks:** taken from confirmed, non-dominated, costed packages. Threshold: 10% of baseline emissions. An optional budget limits the picks.

| Objective | Label |
|---|---|
| `lowest_cost_meeting_threshold` | Lowest-cost package cutting emissions by at least 10% |
| `largest_carbon_saving` | Largest carbon saving |
| `best_carbon_per_pound` | Most carbon saved per pound among packages cutting at least 10% |

- **Ties:** larger carbon saving, then lower cost, then fewer measures, then package id.
- **Fallbacks**, each stated explicitly and never a silently lowered threshold:
  - no package reaches 10%
  - no valid cost data
  - no package cuts emissions
  - only conditional packages
  - baseline unavailable
- **Each package records:** cost provenance, unvalidated impacts (glazing, thermostat, heat pump), the D14 combination warning, and its survival under sensitivity.

## 14. Sensitivity (`sensitivity.py`)
A *limited one-at-a-time analysis, not a confidence interval*. The package search is rerun under 12 variants:
- baseline ±15%
- SCOP 2.5 and 3.5
- space/water gas split 65/35 and 85/15
- cooking-gas share ×½ and ×2
- impacts at the catalogue low and high ends
- headline impacts instead of segment-adjusted (D15)
- NEED-calibrated combinations (D17)

For each featured pick it reports `survives k/12` and the runs under which it changed.

**Not tested:** roof orientation and shading, occupancy, weather, ventilation, installation quality, prices, heat-pump sizing.

## 15. Decision audit (`audit.py`)
Generated from the computed result, never hand-written. It contains:
- the baseline and its provenance
- feasibility for each measure
- the packages considered, and why each was excluded (dominated, conditional, missing cost)
- the objective behind each featured pick
- the winner, one meaningful alternative, and the main factors that separate them
- survival under each sensitivity run
- the unknowns
- the versions and the scenario id

## 16. Scenario builder and portfolio
- **`scenario_builder.build(request)`** is the only writer of numbers. Its steps:
  1. home
  2. baseline
  3. feasibility
  4. simulate (requested measures, or every non-infeasible measure)
  5. carbon
  6. score before and after
  7. packages
  8. sensitivity (if requested)
  9. valuation (`not_estimated`, "audit pending", while the value gate is closed, D10)
  10. audit
- **`scenario_id`** = SHA-256 of the canonical home state, the request (measures sorted) and the config versions. `data_timestamp` is excluded.
- **Blocked measures** never get a computed impact.
- **Privacy:** the output has no address, postcode, UPRN or certificate number; only `display_label` and the outward code.
- **`portfolio.portfolio(top_n, split)`:** Poor and Very poor homes ranked by the improvement potential of their confirmed feasible package. Unavailable potential is ranked last and shown as null, never 0.
  - **Summary:** counts by class, median potential, total carbon potential (t/yr), share of homes with incomplete data.
  - Flags come from the score class (per-m² intensity), so large homes are not flagged for their total use.

## 17. Entry points for the API owner (`backend/app/services/api.py`)
`backend/app/main.py` does not exist yet; the API owner should call:

```python
build(req: ScenarioRequest) -> ScenarioResult                     # full scenario, what-if = new request
assess(home_id: str) -> list[FeasibilityItem]
score(home_id: str) -> ScoreResult
search(home_id, assumptions=None, threshold_pct=10.0, budget_gbp=None, user_reading=None) -> PackageSearch
portfolio(top_n: int = 50, split: str | None = None) -> dict
```

**What-if requests:** change `ScenarioRequest.measures`, `assumptions` or `user_reading`, call `build()` again, and pass the new `ScenarioResult` to the LLM. The LLM never computes numbers.

## 18. Performance (engine-v1; see §19 for v2)
Measured on 300 random test homes:

| Call | p50 | p95 | max |
|---|---|---|---|
| `build()` with package search | 1.2 ms | 2.9 ms | 5.6 ms |
| `build()` with sensitivity | 5.7 ms | 22.9 ms | 52 ms |
| `portfolio()` over all 65,872 homes (cached afterwards) | | | about 5 s |

## 19. engine-v2 refinements (D15–D18)
| Refinement | Where | Default | Switch | Changes |
|---|---|---|---|---|
| Segment-aware NEED impacts | `services/impacts.py` | on | `Assumptions.segment_impacts` | loft, cavity, solid wall, PV savings per home |
| Electrically heated homes | `units.decompose`, `simulator._apply` | on once `configs/electric_heating_split.json` exists | (file present) | fabric, glazing, thermostat, heat pump for `heating_type = electric` |
| NEED-calibrated combinations | `services/combination.py` | engineering headline + calibrated reference | `Assumptions.combination_mode` | `combination_check`, `PackageResult.calibrated` |
| Boiler efficiency by heating rating | `units.boiler_efficiency` | on | `Assumptions.boiler_efficiency` override | heat-pump electricity only |

- **Reconciliation:** unchanged and still asserted. Electric end uses (`elec_space`, `elec_water`) are part of `elec_import`, and PV applies to gross electricity (`elec_gross`).
- **Demo A** (hand-checked, `tests/fixtures/hand_calc_demo.py`):
  - segment-adjusted impacts: loft 3.73%, cavity 16.40%, PV 11.01%;
  - package: gas 20,957.4, electricity −3,544.0 kWh, improvement potential 68.60%, carbon 3,310.6 kg/yr;
  - NEED-calibrated reference: carbon 3,216.8 kg/yr (pooled factor 0.484).
- **Timing:** for a test home with 6 candidate measures (64 packages), `build()` with packages takes ~23 ms and with sensitivity ~181 ms (engine-v1 on the same home: 11 ms and 105 ms). Not yet re-measured on the 300 random York test homes.

## 20. engine-v3 (D19–D29)
| Area | Change | Switch / config |
|---|---|---|
| PV (D19) | NEED % applies to baseline electricity, not heat-pump electricity; capped at import | — |
| Loft rule (D20) | roof type parsed from the EPC description; flat → infeasible; roof room / rafters / thatch / unknown type → needs_verification; depth sets suitability; ≥ 270 mm → infeasible; pre-1919 planning note | `engine_params.loft`, `.planning` |
| Segments (D15 rev.) | region + largest single adjustment; backfitted effects once calibrated | `engine_params.segment_impacts.combine`, `engine_calibration.segment_effects` |
| Area scaling (D21) | L1 benchmarks × (area / band reference)^β, in baseline and score; score params v2 | `engine_calibration.area_elasticity` |
| Missing parts (D22) | train-mean prior instead of 50 (renewables by EPC age) | `engine_calibration.missing_part_priors` |
| Costs (D23) | partial glazing × single-glazed share; size scaling once the York reference area is known | `services/costs.py`, `engine_params.costs` |
| SCOP (D24) | 2.44 / 2.80 / 3.5 (Electrification of Heat) | `engine_params.heat_pump_scop` |
| Thermostat (D25) | 10 / 7.5 / 5% by existing controls | `engine_params.smart_thermostat_by_controls` |
| Bills (D26) | per fuel with standing charges at the Ofgem cap; gas standing charge saved only if no gas is left; price what-ifs | `configs/energy_prices.json`, `Assumptions.gas_price_p` / `elec_price_p` |
| Grants and finance (D27) | BUS £7,500 (£9,000 off-gas uplift window); selection on net cost; payback; illustrative loan | `configs/grants.json`, `configs/finance.json`, `Assumptions.apply_grants` |
| Uncertainty (D28) | 300 seeded draws; P10/P50/P90, P(carbon cut ≥ 10%), P(bill falls) | `ScenarioRequest.include_uncertainty` |
| Portfolio (D29) | fabric-only potential, net cost, bill, payback, kg CO₂e/£; `rank_by` | `portfolio(rank_by=...)` |

- **New outputs:**
  - `ScenarioResult`: `bills`, `finance`, `uncertainty`;
  - `standalone[m]`: bill saving, gross/net cost, grants, payback;
  - `PackageResult`: `grants_gbp`, `net_cost_gbp`, `bill_saving_gbp`, `payback_years`;
  - `PackageSearch.cost_basis`.
- **Sensitivity:** 13 runs (adds `no_grants`).
- **Demo A (hand-checked):**
  - package: gas 20,957.4, electricity −4,667.1 kWh/yr, improvement potential 64.18%, carbon 3,148.9 kg/yr;
  - money: bill saving £442/yr; £25,087 gross, £7,500 grant, £17,587 net; payback 39.8 years;
  - cavity wall pick: £1,000, £238/yr, payback 4.2 years.
- **Timing** (test home with 6 candidate measures):

| Build | Time |
|---|---|
| With packages | ~26 ms |
| + sensitivity (13 runs) | ~225 ms |
| + uncertainty (300 draws) | ~150 ms |
