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
