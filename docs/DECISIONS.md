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
