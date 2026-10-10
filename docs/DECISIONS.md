# Decisions log

Each entry: decision, why, alternatives, consequences. Date 2026-10-10 unless noted.

## D1. Study area = City of York (E06000014)
- **Why:** single local authority with 95k EPC certificates (65,872 homes) and 4,095 Land Registry sales in 2025-26, enough for matching and splits while keeping the full pipeline fast; mix of pre-1900 solid-wall terraces, inter-war semis and modern estates. LA code verified in EPC data (`local_authority_label` = "York"), district "YORK" in Land Registry.
- **Alternatives:** whole of England and Wales (too slow to iterate), North Yorkshire (larger, more rural).
- **Consequence:** results describe York; NEED benchmarks are regional (Yorkshire and The Humber), not York-specific.

## D2. Benchmarks split by main heating fuel
- **Decision:** NEED benchmark cells are keyed by `need_main_fuel` (gas / not gas) in addition to property type x EPC band x floor-area band (fallback: drop area, then type; min 30 homes per cell).
- **Why:** electricity use of electrically heated homes is very different from gas-heated ones; pooling them would bias both. Gas benchmarks use only gas-heated, metered homes.
- **Consequence:** homes with mains gas that is not the main heating fuel get no gas baseline (status recorded).

## D3. Secondary glazing counted as "double"
- **Why:** canonical glazing categories are single/partial/double/triple; secondary glazing is a second pane layer with performance closer to double than single. Affects 671 York homes (latest certificate mentions secondary glazing in glazed_type or windows_description).
- **Consequence:** glazing upgrade rules treat secondary-glazed homes as already double; documented in mappings/glazing.csv.

## D4. "Smart controls" proxy
- **Decision:** `controls = smart` when the EPC records "time and temperature zone control" (TTZC).
- **Why:** EPCs do not record internet-connected thermostats; TTZC is the highest control level in RdSAP.
- **Consequence:** provenance `assumption`; the thermostat measure is offered to homes without TTZC.

## D5. Electricity emission factor includes T&D losses
- **Finding (from `dataset/ghg/...flat-format-revised.xlsx`):** 0.14395 kg CO2e/kWh = Scope 2 "UK electricity / Electricity generated" 0.13096 + Scope 3 "Transmission and distribution / T&D- UK electricity" 0.01299. It **includes T&D losses** and **excludes well-to-tank** (0.03682 + 0.00359).
- **Why keep it:** savings are measured at the home's meter, so upstream grid losses avoided by reducing consumption should be counted. Gas uses 0.18231 (Scope 1, gross CV) to match metered kWh.
- **Alternative:** generation-only 0.13096 (Scope 2 reporting convention); would lower electricity-related carbon by ~9%.

## D6. Baselines are population benchmarks, not meter readings
- **Why:** NEED (metered) is anonymised and cannot be linked to EPC homes; no York meter data is available.
- **Consequence:** `baseline_*_kwh` = median of similar homes in the region (provenance `population_benchmark`); intensity percentiles (score-params-v1) and savings describe typical homes of each type, not the individual household. Customer-provided readings should replace benchmarks when available.

## D7. EPC `energy_consumption_current` unit
- **Finding:** official data dictionary: "estimate of the energy currently used to heat, light, and provide hot water over a year", kWh/m²/year. It does not say primary vs delivered.
- **Consequence:** our column name `epc_predicted_consumption_kwh_m2_primary` encodes an unverified assumption; treat it as "EPC modelled energy per m²" and do not use it for the metered-intensity score component.
- **Update (2026-10-10):** `homes_tagged.parquet` adds `epc_modelled_energy_kwh_m2` (same values, provenance observed); the old column is deprecated, kept for backward compatibility; homes.parquet not rebuilt.

## D8. Retrofit cost source
- **Decision:** costs from York EPC `indicative_cost` texts (certificates 2022+), p25/median/p75 of range midpoints, plus assessor range bounds.
- **Why:** repo data, region-specific, citable; no external figure needed.
- **Caveat:** these are software default ranges, not installation prices; heat pump is a single text (low confidence).

## D9. Gas end-use shares split into three quantities (catalogue cat-v2)
- **Finding:** in cat-v1, `space_share` = 0.75 was a share of *total* gas and `other_gas_share` = 0.25 was defined as "1 - space_share: hot water + cooking". It was neither (a) cooking-only nor (b) the hot-water share of heat-and-water gas, and the heat-pump formula referred to a water share that was never defined.
- **Evidence:** DESNZ ECUK 2026, End uses Table U3 (domestic natural gas by end use, UK), mean 2021-2025: space heating 74.95%, water heating 22.01%, cooking 3.05%; space = 77.3% of space+water gas. https://www.gov.uk/government/statistics/energy-consumption-in-the-uk-2026 (local copy configs/reference_docs/ECUK_2026_End_Use_tables.xlsx). NEED cannot split end uses (annual totals only).
- **Change:** `other_gas_share` = 0.0305 (cooking etc., published national average, configurable); `space_share_of_heat_water_gas` = 0.75 and `water_share_of_heat_water_gas` = 0.25 (assumptions as specified, sum to 1). Derived space share of total gas = 0.75 x (1 - 0.0305) = 0.7271 (ECUK: 0.7495). Glazing/thermostat conversions and the heat-pump heat formula now use these explicitly; heat pumps leave cooking gas in place.
- **Open point:** ECUK suggests 0.77/0.23 rather than 0.75/0.25; kept 0.75/0.25 per instruction (status assumption).

## D10. Value-model go/no-go gate
- **Decision:** the property-value model is enabled only if (1) manual audit precision of linked sale-to-EPC matches >= 0.90 on the 50-row audit sample (`match_audit_sample.csv`, column `correct`), (2) matched sales >= 500, and (3) a coverage check after training (pending). Evaluated by `pipelines/audit_sales_matches.py` -> `configs/value_gate.json`.
- **Why:** wrong matches attach the wrong EPC rating to a sale price and bias any rating-price association.
- **Caveat:** precision from 50 rows has a wide 95% Wilson interval (e.g. 45/50 -> 0.79-0.96). Until the audit is filled in, status is `audit_pending` and the gate is closed.
- **Note:** this entry was added on 2026-10-10 because the gate was referenced as "decision 10" but had not been recorded.

## D11. Space/water gas split 0.77/0.23 (catalogue cat-v3)
- **Decision:** `space_share_of_heat_water_gas` = 0.77 and `water_share_of_heat_water_gas` = 0.23, replacing the 0.75/0.25 assumption in cat-v2 (D9 open point closed).
- **Why:** DESNZ ECUK 2026 Table U3 (UK domestic gas by end use, mean 2021-2025) gives space heating = 77.3% of space + water gas; rounded to 2 dp. Still status `assumption` (national average, not York-specific, NEED cannot split end uses).
- **Also in cat-v3:** `global.heat_pump_scop` {2.5, 3.0, 3.5} so the engine reads SCOP from one global, not from the measure block (values unchanged).
- **Consequence:** derived space share of total gas = 0.77 x (1 - 0.0305) = 0.7465 (ECUK direct: 0.7495). Glazing and thermostat savings rise ~2.7% relative to cat-v2; heat-pump totals are unchanged (they use space + water together).

## D12. Engine feasibility: unknown wall/roof type -> needs_verification
- **Decision:** wall type is read from the EPC walls description with the catalogue regexes. "Average thermal transmittance ..." (new-build U-value), "SAP05:Walls" and system-built/basement walls give type unknown -> `needs_verification` for cavity and solid wall. Timber frame and park homes are known non-masonry -> infeasible for both.
- **Roof:** roof `not_applicable` is infeasible for loft insulation only when the description says a dwelling or premises is above; otherwise (e.g. "SAP05:Roof") it is `needs_verification`.
- **Why:** the spec requires missing critical inputs to give needs_verification, never infeasible. This differs from the foundation note for demo home C ("roof N/A: loft infeasible"): its roof description is "SAP05:Roof", not a dwelling above, so the engine reports needs_verification.
- **Flats:** no floor-level column exists in homes_tagged; "another dwelling above" is the top-floor proxy. Solar PV stays infeasible for flats/maisonettes (catalogue rule, shared roof).

## D13. Non-gas-heated homes: fabric/glazing/thermostat savings not estimated
- **Decision:** for homes whose space heating is not on gas (electric, oil, other, heat pump), fabric, glazing and thermostat impacts are `not_estimated` (reason `heating_not_on_gas`); heat pump is `not_estimated` (`no_gas_to_displace`); solar PV is estimated.
- **Why:** NEED impacts are % of gas; the baseline electricity of an electrically heated home is not split into heating vs appliances, so any saving would rest on an invented split. Conservative option: abstain and say so.
- **Consequence:** ~18% of York homes get no fabric savings estimate; feasibility is still reported. A future electric end-use split (e.g. from NEED electricity by heating type) would lift this.

## D14. Simulator overestimates NEED combination savings; not tuned
- **Finding:** `docs/validation/simulator_vs_need.json`: simulated combined savings exceed NEED Table 2 medians by +5.6 to +13.8 pp (tolerance ±5 pp). NEED cavity+loft (8.4%) is below NEED cavity alone (12.0%), so no multiplicative model can match both.
- **Decision:** keep the transparent multiplicative model (no fitted combination discount); attach a warning to every package with two or more fabric/controls measures; report the gap in ENGINE.md.
- **Alternative:** an empirical combination factor fitted to Table 2 (4 rows; would be overfit and hide the uncertainty).
- **Update (engine-v2):** the factor is now reported **next to** the engineering estimate as a NEED-calibrated reference, never instead of it (D17).

## D15. Segment-aware NEED impacts (empirical-Bayes shrinkage)
- **Decision:** loft, cavity wall, solid wall and solar PV use the NEED impact for the home's segments (EPC band, property age, property type, region) instead of the single national median. Each segment's deviation from the headline median is shrunk by w = τ² / (τ² + se²), where se is the sampling error of the segment median (1.2533 × (IQR/1.349)/√n) and τ² the between-segment variance left after removing sampling noise. The home's shrunk deviations are added together, then the result is floored at 0. Code: `backend/app/services/impacts.py`. Settings: `configs/engine_params.json` (`segment_impacts`).
- **Why:** the catalogue already held the NEED segment tables but did not use them. Segments differ by more than noise for several measures: cavity wall in an E–G detached home is ~16% of gas versus 12% nationally, and solid wall in pre-1919 homes is ~11% versus 17%. Shrinkage stops noisy cells from driving the estimate: loft by EPC band and by age has no between-segment variance beyond noise, so it stays at the headline.
- **Alternatives:** raw segment medians (noisy, can go negative), a single best segment (throws information away), a fitted regression (NEED publishes margins only, not joint cells).
- **Revision (engine-v3):** adding the segment adjustments double-counted, because EPC band, age and type are correlated. Example: solid wall in a pre-1919 mid-terrace EPC E home came out at 2.8% against a 17.3% headline. The default is now the **region adjustment plus the single largest non-region adjustment** ("max" rule). Once `make engine-cal` has run, the engine instead uses **backfitted additive effects**, fitted so that their York-weighted average in each segment reproduces the NEED segment median.
- **Consequences (original):** segments are combined additively, assuming independence (NEED does not publish joint cells). Flats get no property-type adjustment because NEED reports none. Every York home gets the Yorkshire and the Humber region adjustment. Each simulator step note shows the headline and the adjustment, and `Assumptions.segment_impacts = False` restores the headline. A sensitivity run (`headline_impacts`) checks whether the featured picks depend on it. The NEED combination validation (`pipelines/validate_simulator.py`) and the hand-calculated reference cases stay on headline impacts.

## D16. Electrically heated homes: heating share of electricity from NEED benchmarks
- **Decision:** for `heating_type = electric`, the heating share of baseline electricity is 1 − (median electricity of gas-heated homes) / (median electricity of non-gas-heated homes) in the same NEED property type × EPC band cell, falling back to the EPC band, then to all homes. Each side needs ≥ 30 homes, and the share is clipped to [0, 0.9]. The share is split 0.77/0.23 into space and water heating, as for gas. Fabric measures (converted from the NEED % of total gas with the same space share, 0.77 × (1 − 0.0305)), glazing and thermostat then cut electric space heat. A heat pump replaces the electric space + water heat (efficiency 1.0), so it saves heat × (1 − 1/SCOP) of electricity. Built by `pipelines/build_electric_heating_split.py` → `configs/electric_heating_split.json`.
- **Why:** D13 left about 18% of York homes (e.g. demo B) with no savings estimate. The NEED benchmarks already contain both groups of homes, so the split comes from data, not from an invented end-use share.
- **Caveats:** NEED's "not gas-heated" group also includes oil, LPG and solid-fuel homes, whose heating is not electric, so the share is **conservative** for direct-electric homes. Oil and other heating types are still not estimated, because there is no metered baseline for those fuels.
- **Consequence:** until the split file is built, the engine keeps the D13 behaviour and says why ("electric heating split not built").

## D17. NEED-calibrated reference for combined packages (supersedes the "no fit" part of D14)
- **Decision:** the engineering (sequential multiplicative) estimate stays the headline number. Packages with two or more fabric/controls measures also report a **NEED-calibrated reference**: every fabric/controls impact is multiplied by a factor f solved by bisection, so that the simulated saving on the validation reference home equals the NEED Table 2 median. The factors are 0.559 for cavity + loft, 0.712 for solid wall + loft, 0.409 for solid wall + controls, 0.407 for solid wall + loft + controls, and 0.484 pooled (NEED-n-weighted) for other combinations. Built by `pipelines/build_combination_calibration.py` → `configs/combination_calibration.json`. Output: `ScenarioResult.combination_check` and `PackageResult.calibrated`; mode switch `Assumptions.combination_mode`.
- **Why:** D14 showed that packages are overestimated by 5.6–13.8 pp. Showing both figures is more honest than either one alone. Heat pump and PV are re-simulated on the calibrated state, so per-fuel figures still reconcile.
- **Caveats:** four combinations cannot separate in-use effects from selection effects (NEED cavity + loft is below cavity alone), so f is a reference point, not a physical constant. A sensitivity run (`need_calibrated_combinations`) reports whether the featured picks survive it.

## D18. Existing boiler efficiency from the EPC heating rating
- **Decision:** the gas boiler's seasonal efficiency is taken from its EPC main-heating rating: Very Good 0.89, Good 0.85, Average 0.75, Poor 0.67, Very Poor 0.60, with 0.85 when unknown (`configs/engine_params.json`). A scenario override (`Assumptions.boiler_efficiency`) still wins.
- **Why:** a single 0.85 for every boiler overstates the useful heat an old non-condensing boiler delivers. That heat is what a heat pump must replace, so the single value overstates the heat pump's added electricity for those homes.
- **Status:** **assumption.** The values approximate SAP Table 4b default seasonal efficiencies (condensing ~84–89%, non-condensing 1998+ ~73–74%, pre-1998 ~65%) and treat the EPC rating as a proxy for boiler type. They were **not checked against the table text** in this build because the BRE site was unreachable, so verify them against SAP 10.2 Table 4b. Good = 0.85 keeps the cat-v3 default, so demo A (boiler rated Good) is unchanged by this decision.
- **Consequence:** only heat-pump results change, because fabric and controls gas savings do not depend on boiler efficiency (it cancels out). The value used and its source are echoed in `assumptions_used` and the decision audit.

## D19. Solar PV saving on baseline electricity, not heat-pump electricity
- **Finding:** the NEED PV impact (12.2% of grid electricity) was applied to grid electricity *including* heat-pump electricity. Demo A's PV saving went from 415 to 904 kWh/yr once a heat pump was added, with the same panels.
- **Decision:** the PV % applies to the home's baseline electricity before any retrofit, and never offsets more than the current import. Exports are still not credited (conservative).

## D20. Loft rule reads the roof type; planning note for pre-1919 homes
- **Finding:** loft insulation was offered, with High suitability, for flat roofs, rooms in the roof, rafter-insulated roofs and thatch.
- **Decision:** the roof type is parsed from the EPC description:
  - flat → infeasible;
  - room in roof, insulated at rafters, thatched, or type not stated (U-value or code only) → needs_verification;
  - pitched → feasible. The recorded depth sets suitability (≤ 100 mm → High); ≥ 270 mm (`engine_params.loft`) → infeasible.
- **Planning:** pre-1919 homes get a note to check conservation-area and listed-building status for solid wall insulation and PV. York has many conservation areas, but no planning layer is loaded, so this is a note, not a rule.

## D21. Benchmark scaled within its floor-area band (needs `make engine-cal`)
- **Finding:** every home in a NEED cell (type × EPC band × floor-area band × fuel) gets the same kWh, so kWh/m² falls as area rises *within* a band. With the same benchmark, a 151 m² home scored 3.3 intensity points and a 199 m² home 10.6.
- **Decision:** `benchmark × (floor area / band reference area)^β`. β per fuel is fitted on NEED across floor-area bands within type × EPC band × fuel cells, and the reference area is NEED's representative area for the band. It applies only to L1 cells, which include the area band. Score params are refrozen as v2 on the scaled baselines. Until calibrated, there is no scaling.

## D22. Missing score parts take the typical value, not 50 (needs `make engine-cal`)
- **Finding:** a missing part was scored 50. With PV unrecorded, a home scored +5.0 points against the same home with PV recorded as none (5,735 train homes, mostly old EPCs that predate PV).
- **Decision:** the headline uses the train mean of that part among homes where it is observed. Renewables is split by EPC age, because PV is rarer on old certificates. range_low/high stay 0/100, and the note says which prior was used. Until calibrated, the value stays 50.

## D23. Home-specific costs
- **Partial glazing:** cost × single-glazed share; 50% when the share is not recorded. Demo A paid £4,900 for 13% of its windows before.
- **Size:** cost × (floor area / York median floor area)^γ, with γ = loft 1.0, glazing 1.0, walls 0.75, heat pump 0.3, PV and thermostat 0, clamped to 0.5–2.0. γ values are assumptions. Size scaling needs `make engine-cal` for the York reference area.

## D24. Heat-pump SCOP from UK field evidence
- **Decision:** SCOP low/mid/high = 2.44 / 2.80 / 3.5, replacing 2.5 / 3.0 / 3.5. 2.80 is the median SPF of air-source heat pumps in the Electrification of Heat demonstration, across home types; 2.44 is its cold-day median, used as a conservative low; 3.5 remains an assumption. Source: Energy Systems Catapult, EoH interim heat pump performance data analysis (2023). Set in `engine_params.heat_pump_scop`, which overrides the catalogue.
- **Effect:** heat-pump electricity +7%; demo A carbon saving falls accordingly.

## D25. Thermostat saving placed by the controls already installed
- **Finding:** the same 7.5% saving was applied whether a home had no controls or full controls.
- **Decision:** the brief range is placed by current controls: none → 10% (high), timer → 7.5% (mid), full → 5% (low). The scenario impact level still shifts one step. This is an assumption.
- **Validation homes:** the NEED "heat controls" validation homes use timer controls (an upgrade from basic controls), which keeps them at the mid value.

## D26. Annual bills per fuel at the Ofgem price cap
- **Decision:** bill = unit cost + standing charges, at the Ofgem cap for 1 Oct – 31 Dec 2026 (Direct Debit, GB average):
  - electricity 26.32p/kWh + 54.83p/day;
  - gas 7.97p/kWh + 29.68p/day (`configs/energy_prices.json`; rates from press coverage citing Ofgem, to verify on the Ofgem page).
  - The gas standing charge is saved only when no gas is left: cooking gas keeps the connection.
  - Solar export is not credited, so PV bill savings are conservative.
  - What-if unit rates (e.g. a heat-pump tariff) go through `Assumptions.gas_price_p` / `elec_price_p`.
- **Why:** customers decide in £. Demo A shows why carbon alone misleads: the heat pump cuts ~2.9 t CO₂/yr but is roughly bill-neutral (−£4/yr) at capped rates, while cavity wall insulation alone saves £238/yr for £1,000.
- **Outputs:** `ScenarioResult.bills`, `standalone[m].bill_saving_gbp`, `PackageResult.bill_saving_gbp`.

## D27. Grants, net cost, payback and an illustrative loan
- **Grants:** Boiler Upgrade Scheme £7,500 for an air-source heat pump. Off-gas homes get £9,000 for applications 21 Jul 2026 – 31 Mar 2027 (temporary uplift). Grants are evaluated at a fixed `as_of` date (`configs/grants.json`) so results stay reproducible. Eligibility: England or Wales, replacing gas, oil, electric or other heating. The grant is capped at the measure cost and is always labelled "subject to eligibility". Insulation grants (ECO4, GBIS) are income-based and not modelled.
- **Selection:** package selection (Pareto, featured picks, carbon per £) uses the cost net of grants (`Assumptions.apply_grants`, default on). Gross cost is always shown. A `no_grants` sensitivity run (13 runs in total) shows whether picks depend on the grant.
- **Finance:** simple payback = net cost / annual bill saving, with none when the bill does not fall. The monthly repayment at an illustrative 7.0% APR over 10 years (`configs/finance.json`, **not a Lloyds product or offer**) is shown next to the monthly bill saving.
- **Demo A, full package:** £25,087 gross, £7,500 grant, £17,587 net, £442/yr bill saving, 39.8-year payback. The cavity wall pick pays back in 4.2 years.

## D28. Monte Carlo ranges for a home's package (model-input uncertainty)
- **Decision:** `ScenarioRequest.include_uncertainty` runs 300 draws, seeded from the scenario id so the result is reproducible. What varies:
  - NEED impacts: headline triangular(low, mid, high) + segment adjustment + normal(0, empirical-Bayes posterior sd);
  - glazing: uniform over the brief range;
  - thermostat: uniform over the levels next to its controls placement;
  - SCOP: triangular 2.44 / 2.80 / 3.5;
  - boiler efficiency: ±0.05;
  - space/water split: 0.65–0.85;
  - baseline per fuel: lognormal household spread around the NEED cell median, when `make engine-cal` has built it. Never varied for a user reading or an observed zero.
- **Reports:**
  - P10 / P50 / P90 of gas, electricity, purchased energy, carbon (kg and %), bill saving and improvement potential;
  - P(carbon cut ≥ 10%) and P(bill falls);
  - what was and was not varied.
- **Not compounded:** NEED's household outcome spread (p5–p95, which includes occupancy and other unrelated changes) is shown per measure as context. Compounding it across measures would overstate the spread, because that noise is per household, not per measure.
- **Label:** "model-input uncertainty … not a confidence interval".
- **Demo A:** carbon 3.09–3.25 t/yr (P10–P90); bill saving £343–£626/yr; P(bill falls) 1.0. Build time ~150 ms.

## D29. Portfolio: fabric-only potential, cost metrics and ranking options
- **Finding:** ranking by improvement potential of "all feasible measures" mostly ranks by heat-pump eligibility; a heat pump alone gives ~60% purchased-energy reduction in a gas home.
- **Decision:** each flagged home also reports:
  - fabric/controls-only potential and carbon;
  - gross cost, grants and net cost;
  - bill change and payback;
  - kg CO₂e per £ (net).
  - `portfolio(rank_by=...)` accepts improvement_potential (the brief's default, unchanged), fabric_potential, carbon_per_pound or carbon_saving. Unavailable values always rank last.

## D30. Engine calibration generated but not applied during the ML phase (date 2026-10-11)
- **Finding:** M0 step 1 runs `make engine-cal` and `make elec-split`. Writing `configs/engine_calibration.json` and `configs/electric_heating_split.json` (and the refrozen score params v2) turns 17 currently passing tests red. The suite and the hand-calculated demo fixtures (`tests/fixtures/hand_calc_demo.py`, "no engine imports") are written for the **uncalibrated** engine, e.g. `test_area_factor_only_for_l1_cells_and_when_calibrated` asserts "no calibration file".
- **Decision:** keep the engine uncalibrated in `configs/` so existing tests stay green. The calibration outputs are kept, untracked, in `data/processed/region=york/engine_cal_candidate/` (engine_calibration.json, electric_heating_split.json, score_params_v2.json). ML milestones that need a calibrated quantity (M4 B0 area scaling, D21) compute it from train data inside the ML pipeline and say so.
- **Why:** conservative: the plan's rule "existing tests must stay green" and its instruction to calibrate conflict; changing hand-checked fixtures is an engine decision, not an ML one.
- **Also recorded:** 4 tests fail on the unmodified branch before any ML change (`test_demo_homes`, `test_demo_a_packages`, `test_demo_a_matches_hand_calc`, `test_a_rated_high_g_rated_low_across_dataset`): the local York build differs from the demo expectations (e.g. demo A loft not feasible). The ML phase adds no new failures and does not edit them.

## D31. Wider privacy guard for ML reads (date 2026-10-11)
- **Decision:** `backend/app/ml/privacy.py` never loads, besides the `restricted_address` role: `paon`, `saon`, `street`, `locality`, `town`, `district`, `county`, `sale_addr*`, `epc_address`, `address_key` (address-derived), and `uprn`/`uprn_source` (an Ordnance Survey address reference). Any column whose name contains "addr", "postcode" or "posttown" is restricted except `postcode_outward`, `postcode_district` and `postcode_sector`. Columns are selected from the parquet schema **before** reading, so restricted values never enter memory; the full postcode is read only inside `safe_read_parquet(derive_postcode=True)` to derive the outward code and sector, then discarded.
- **Why:** the sales table holds more address fields than the plan lists; the conservative reading is to exclude every address-like field. `property_id` (UPRN-based for most homes) stays as the join key only, as in the engine.

## D32. ML feature layer choices (ml-features-v1, date 2026-10-11)
- **One code path:** `state_from_certificate` maps a certificate row to homes_tagged column names and reuses the engine's `home_from_row`, so a home and its latest certificate give identical features (checked on 3,000 York homes: 0 mismatches; test on 60 real homes).
- **HomeRecord** gains optional fields read from homes_tagged (windows rating, age start, floor description, main fuel, main heating description, habitable rooms, transaction type, lodgement date, postcode sector derived from the postcode). The scenario id changes because the hashed home state is larger; no test fixes an id.
- **Extras parsed from description text** (allowed by plan §0.2): wall / roof / floor U-values ("Average thermal transmittance"), monotone −1 in the SAP model; floor insulation as a level (none 0, limited 1, insulated 2) instead of a flag, monotone +1; `solar_water_heating` monotone +1.
- **Not used:** `epc_age_years` (it is the reference date minus the lodgement date, collinear with `lodgement_year`).
- **Imputation consistent with the state:** partial glazing with unknown share = 50% (the score's assumption) with a `multi_glaze_pct_missing` flag; double/triple = 100%, single = 0%; no PV recorded = 0% of roof. Everything else missing stays NaN plus a flag.
- **Inference year:** `lodgement_year` at inference is the model's reference year stored in its meta.json (the latest lodgement year in training), not today's date, so predictions do not drift with the calendar.
- **After-retrofit features:** `score.apply_state_effects` plus loft depth raised to 270 mm (pitched roofs with a known depth), wall insulation level raised to 2 (known level), heat pump → heating family heat_pump and fuel electricity. A missing value is never turned into a known one, so every monotone input moves between known values; new PV keeps the recorded roof share (unknown size, conservative).

## D33. Value-model state features exclude element ratings (date 2026-10-11)
- **Decision:** the value model's state features are the SAP score at sale, size, rooms, age, type/built form, wall/roof/floor type, heating family, fuel, mains gas, glazing and PV, plus location; the EPC element ratings (walls, roof, windows, heating...) are left out.
- **Why:** the ratings are components of SAP; including them would split the energy-efficiency signal across correlated inputs and make the "same home at SAP + ΔSAP" comparison understate (or arbitrarily allocate) the SAP effect. Conservative and interpretable.

## D34. Modelled EPC change shown next to the score; headline EPC part changes only on request (date 2026-10-11)
- **Plan:** M2 makes the after-retrofit energy-efficiency part `clip(observed SAP + ΔSAP, 1, 100)`.
- **Conflict:** existing tests and the hand-calculated demo fixtures assert the after-score EPC part is `unchanged_epc_not_reassessed`.
- **Decision:** `score_after` always attaches the modelled change (`ScoreResult.epc_change`: ΔSAP, indicative SAP and band after, model version, provenance `modelled`) and `rating_after_indicative`. The EPC part of the headline uses the modelled SAP only when `ScenarioRequest.use_modelled_epc = True` (status `modelled_epc_change`, provenance `modelled`). Default behaviour and the hand-checked numbers are unchanged; the "E → C" story is still shown.
- **Why:** conservative (a modelled number does not silently replace an observed one) and keeps the engine tests valid.

## D35. Value features for homes with no sale (date 2026-10-11)
- **Decision:** a York home that is valued without a sale gets: Land Registry type from property type and built form (flats and maisonettes → Flat/Maisonette; houses and bungalows → Detached / Semi-detached / Terraced), tenure leasehold for flats and freehold otherwise, not new build, the latest sale month in the data. The outward code and the sector's train target encoding (unseen sector → train mean) give location; an unseen outward code drops the GBP value (the % range is still given).
- **Why:** these fields exist only on sales; the mapping is the most common case in York sales (most flats are leasehold). Status assumption.

## D36. Energy model: comparison choices (date 2026-10-11)
- **Rows:** NEED rows with an EPC band only (about 30% of NEED rows have none; York homes always have one; the engine's benchmarks also drop them).
- **B0:** the engine's cell medians (main fuel × type × EPC band × area band, L1 → L2 → L3, ≥ 30 homes) keyed additionally by region, recomputed on the NEED train split, so the comparison covers England and Wales; the Yorkshire subset uses exactly the engine's region. The D21 area scaling is a no-op on NEED rows (one representative area per band).
- **Tuning:** 40 trials, 3-fold grouped CV on a 500k-row stratified (region × EPC band) train subsample (plan: 500k subsample; 3 folds to bound runtime on 4M rows). Objectives l2, huber and l1 on log kWh; the objective is picked on val MAE.
- **Switch:** `use_model_baseline` is true only if **both** fuels pass (≥ 2% MAE gain overall and not worse on Yorkshire).
- **Quantile models** ship only if their mean pinball loss on val beats the cell's own train P10 / P50 / P90 (overall and not worse on Yorkshire). In the Monte Carlo they replace the calibrated lognormal household spread (D28) only where that spread is configured, so an uncalibrated engine is unchanged.

## D37. Recommender fallbacks and comparable scores (date 2026-10-11)
- **Heat pump:** 31 positive labels in York (23 among train homes with a non-infeasible rule): no classifier, rules only.
- **Fallback score:** a measure without a shipped classifier is scored by its train prevalence for the home's property type × age band (B1), so probabilities remain comparable across measures in one ranking.
- **Ranking gate:** the probability order is used only if the ranking beat the engine order (B2) on val NDCG@3; otherwise the service returns the engine order with no probabilities.
- **Install sequence** is always the engine's fixed physical order, shown separately.

## D38. Test split scored once; value estimate enabled (date 2026-10-11)
- **What happened:** after every model, gate and threshold was frozen on validation, `pipelines/ml/evaluate_models.py` scored the test split once (`docs/validation/ml_test.json`; the script refuses to run again while that file exists). Before that, the same code was dry-run on **val** and reproduced the validation numbers exactly, so the test run used the training pipeline's own definitions.
- **Value gate (D10):** the 80% split-conformal interval (calibrated on val) covered 82.1% of 619 test sales, inside 0.75–0.85. With audited match precision 1.00 and 4,000 matched sales, all three conditions pass, so `configs/value_gate.json` status is `enabled` and the valuation service returns the indicative range. It is always labelled as an association with caveats.
- **Tests:** `test_valuation_gated` and `test_abstain_gate_closed` now set a closed gate explicitly (they test the closed-gate behaviour, not the current config).
- **Energy:** no point model ships (both fuels improve on the benchmark by < 2%); the benchmark stays the baseline, quantile models ship (D36).

## D39. LLM layer ported onto the current engine; the engine stays the only writer of numbers (date 2026-10-11)
- **Decision:** `backend/app/llm/` (from `feature/llm-layer`) now reads every number from the engine result through `payload.build_payload` (stable key per number) and `engine_map.to_contract`. The engine exports its after-retrofit totals (`EndUses` computed fields), so the layer no longer recomputes them (the old electricity total ignored electric space and water heating).
- **Grounding:** the LLM still never sees a number (placeholders filled by code); an independent number checker on the final text matches every number to an engine value; an unmatched number triggers one regeneration with feedback, then the deterministic template.
- **Correction to D30:** the four tests listed there as pre-existing failures are fixed: three expected loft insulation for demo A, whose certificate records a flat roof (infeasible under D20; the hand calculation now applies D20), and one read a `homes_scored.parquet` produced during the M0 calibration run (re-scored with the current configs). `make test` is fully green.

## D40. Bills, payback and an illustrative loan may be explained; climate fit and "pays for itself" may not (date 2026-10-11)
- **Why:** these are engine outputs since D26/D27, so the old rule banning any bill or payback sentence would hide engine results. The loan may only be mentioned citing the engine's loan figures and labelled illustrative (not a Lloyds product or offer); mortgages, borrowing and investment advice stay banned.

## D41. What-if requests are validated by the engine's ScenarioRequest; anything invalid is refused with the reason (date 2026-10-11)
- **Supported:** add/remove measures; tariffs (`elec_price_p`, `gas_price_p`), `apply_grants`, `heat_pump_mode` with `heat_pump_partial_share`, `impact_level`, the user's own readings, `include_uncertainty`; budget and situation statements go to the decision-context flow.
- **Conservative choices:** a partial heat pump without a stated share is refused (the engine needs it; no default share is invented); a negative or otherwise invalid value is refused with the schema's message; a question that matches no supported intent, measure or change is declined rather than answered with a full report.
- **Diffs** compare after-retrofit gas, electricity and emissions of the two results (not their savings), so a changed starting point (the user's own reading) is not misread as a rise in emissions.

## D42. LLM evaluation: held-out set, metrics, and fixes made after the first runs (date 2026-10-11)
- **Set:** 53 questions on demo homes A/B/C and five TEST-split homes chosen by rule (`pipelines/llm/make_eval_set.py`), through the FastAPI app on the real engine.
- **Metrics:** groundedness, factual accuracy (independent fresh engine build), unsupported-claim rate, what-if success, refusal correctness (`pipelines/llm/evaluate_llm.py`).
- **Disclosed fixes after the first runs:** price parsing per clause (q31), an evaluation-set regex (q53), payload completeness (step savings, after-retrofit emissions), missing-details coverage (q46); listed in `docs/LLM_EVALUATION.md`.
- **No real-LLM run yet:** no provider key in this environment; the template and mocked-LLM runs are reported, and `make llm-eval` produces the real run when a key is set.

## D43. Web app integrated: /api routes, demo-home source without the York data, LLM routes run the caller's request (date 2026-10-11)
- **Routes:** `backend/app/web_api.py` serves the frontend contract (`frontend/docs/API_CONTRACT.md`) under `/api`: health, demo homes, scenario, budget package search, portfolio (`rank_by`), evidence. They wrap `services/api.py` only; no number is computed in a route. Every response passes the address guard.
- **No York data on the server:** `data/loaders.py` serves the three public demo homes from `data/demo_homes.py` (`configs/demo_homes.json` plus the certificate fields documented in `tests/fixtures/hand_calc_demo.py`) when `homes_tagged.parquet` is absent, and says so (`data_mode = demo_homes` in `/api/health`). They reproduce the hand-calculated fixtures A/B/C exactly (`tests/unit/test_web_api.py`). With the York build present nothing changes.
- **Scenario IDs match:** the `/llm/explain` and `/llm/whatif` bodies take the rest of the engine request (assumptions, reading, packages, sensitivity, uncertainty), so the server explains exactly the scenario on screen (the ID hashes the whole request). What-ifs may change prices, grants and readings (`request_runner`); the web app applies the validated `new_request` through `/api/scenario`, so numbers still come only from the engine.
- **Ranges by default:** the web app requests Monte Carlo ranges with every scenario (`include_uncertainty`, about 0.4 s per run with sensitivity).
- **Offline snapshot:** `frontend/public/fixtures` is regenerated from this engine (`make web-fixtures`), refusing to write unless the demo homes reproduce the hand-calculated fixtures.
- **Serving:** `make web` builds the app in live mode and FastAPI serves it with the API on one port; `CORS_ORIGINS` allows other origins (default: the Vite dev and preview ports).
