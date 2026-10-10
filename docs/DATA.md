# Data documentation: Lloyds PS2 Green Home Score (City of York)

Access date for every source below: **2026-10-10**. Region: City of York local authority (E06000014).
Detailed column dictionary and mapping tables for the York build: `data/processed/region=york/DATA_york.md` and `.../mappings/`.

## 1. Sources

### 1.1 EPC domestic certificates and recommendations (MHCLG)
- **URL:** https://get-energy-performance-data.communities.gov.uk (bulk download `GET /api/files/domestic/csv`, regenerated monthly; our file `lastUpdated` 2026-10-09)
- **File:** `dataset/epc/domestic-csv.zip`, 8,307,563,359 bytes; 19 `certificates-YYYY.csv` + 19 `recommendations-YYYY.csv`, 2008-2026, ~97.6 GB uncompressed (never unzipped; streamed).
- **Licence:** all fields other than address/postcode are Open Government Licence v3.0 (includes OS UPRNs). Address data (address1-3, postcode) are © Ordnance Survey and Royal Mail Group Limited, usable only for the energy-performance purposes listed at https://get-energy-performance-data.communities.gov.uk/guidance/licensing-restrictions (research into energy efficiency of buildings is a permitted purpose). Do not publish address data outside those purposes.
- **Fields used / units:** see `CERT_COLS` in `pipelines/build_region.py`; official definitions in `configs/reference_docs/epc_domestic_data_dictionary.csv` (downloaded from /guidance/data-dictionary). `total_floor_area` m²; `current_energy_efficiency` SAP points; `energy_consumption_current` kWh/m²/year ("an estimate of the energy currently used to heat, light, and provide hot water over a year"; the dictionary does **not** state whether this is primary or delivered energy; use `epc_modelled_energy_kwh_m2` (homes_tagged); `epc_predicted_consumption_kwh_m2_primary` is **deprecated** (unverified 'primary' label, kept for backward compatibility), see DECISIONS D7).
- **Coverage (York):** 95,348 certificates -> 65,872 homes (latest certificate per home); 231,548 recommendation rows on latest certificates.
- **Limitations:** modelled (SAP/RdSAP) not metered; 32% of homes' latest EPC is >10 years old; floor ratings mostly N/A; 'smart' controls not recorded directly; homes never sold or let since 2008 have no EPC.
- **Preprocessing:** `pipelines/build_region.py` (stream filter on `local_authority`, property_id = UPRN or address hash, canonical mappings, NEED-compatible bands). Version: build of 2026-10-10.

### 1.2 NEED anonymised data 2026 (DESNZ): 50k and 4M samples
- **URL:** https://www.gov.uk/government/statistics/national-energy-efficiency-data-framework-need-anonymised-data-2026 (published 2026-06-11). Files: `anon2026_50k.csv`, `anon2026_4million.zip`, metadata `NEED-2026-anonymised-dataset-metadata.ods`.
- **Licence:** Open Government Licence v3.0. Attribution: "Contains public sector information licensed under the Open Government Licence v3.0. Source: DESNZ, National Energy Efficiency Data-Framework."
- **Fields / units:** property type, age band (1-4), floor-area band (1-5), region (ONS code), EPC band, LI/CWI/PV flags and years, main heating fuel (1 gas / 2 not), annual gas (weather-corrected) and electricity kWh 2005-2024 with validity flags.
- **Coverage:** representative stratified samples of England and Wales domestic properties (HMRC Council Tax database Oct 2025).
- **Limitations:** anonymised: **cannot be linked to individual EPC homes or sales**; banded fields only; electricity is metered import (PV homes import less); non-gas fuels (oil/LPG) not metered.
- **Preprocessing:** `need_*.parquet` (baseline = mean of valid 'V' readings 2022-2024; per-fuel status metered / no meter / unavailable). Region benchmarks: `pipelines/build_region.py` step 6 (E12000003, Yorkshire and The Humber).

### 1.3 NEED Impact of measures data tables 2026 (DESNZ), installation year 2023
- **URL:** https://www.gov.uk/government/statistics/national-energy-efficiency-data-framework-need-impact-of-measures-data-tables-2026 (published 2026-06-11).
- **Files used:** `Impact_of_measures_headline_EW_2023.xlsx` (Tables 1-4), `Impact_of_measures_attributes_{loft,cavity_wall,solid_wall,solar,boiler}_EW_2023.xlsx` (Tables 1-8: by EPC rating, age, type, bedrooms, adults, income, tenure, region), `Impact_of_measures_installation_year_EW.xlsx`.
- **Licence:** OGL v3.0 (attribution as 1.2).
- **Units:** fraction of whole-home annual gas (insulation measures) or grid electricity (solar PV); kWh savings also given. Matched intervention/control design.
- **Limitations:** savings vary widely between homes (e.g. loft IQR -16% to +22%); loft figures are mostly top-ups to existing insulation; some regional cells '[no data]'.

### 1.4 HM Land Registry Price Paid Data 2025-2026
- **URL:** https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads (`pp-2025.csv`, `pp-2026.csv`).
- **Licence / attribution:** Open Government Licence v3.0. **"Contains HM Land Registry data © Crown copyright and database right 2026. This data is licensed under the Open Government Licence v3.0."**
- **Fields:** transaction id, price (GBP), date, postcode, property type (D/S/T/F/O), new build, tenure, PAON/SAON/street/locality/town/district/county, PPD category, record status.
- **Coverage:** Jan 2025 - Aug 2026 (1,360,325 rows; 1,140,586 after keeping category A, removing type O and deleted records); York district 4,095 sales.
- **Limitations:** only ~20 months, so repeat sales are rare; no floor area or condition; category A only.
- **Preprocessing:** `data/processed/ppd.parquet`; York matching to EPC homes in `pipelines/build_region.py` step 5 (4,000 linked = 97.7%).

### 1.5 DESNZ Greenhouse gas reporting: conversion factors 2026
- **URL:** https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026 (flat file, revised July 2026); local copy `dataset/ghg/ghg-conversion-factors-2026-flat-format-revised.xlsx`.
- **Licence:** OGL v3.0.
- **Values used** (`configs/emissions_factors.csv`): electricity 0.14395 kg CO2e/kWh = Scope 2 generation 0.13096 + Scope 3 T&D losses 0.01299 (excludes well-to-tank); gas 0.18231 kg CO2e/kWh, Scope 1, gross CV (excludes well-to-tank 0.03021).

### 1.6 Address data: never exposed
The app and API must **never return or display** EPC address fields (`address`, `address1-3`, `raw_address1-3`, `raw_posttown`) or full `postcode`. They are licensed only for energy-efficiency purposes (1.1). In `configs/feature_availability.json` these columns have role `restricted_address` (not features). Demo homes: the committed `configs/demo_homes.json` holds only `home_id`, `display_label`, public fields, `postcode_outward` and engine expectations. Real addresses and full postcodes are written to `data/processed/region=york/demo_homes_internal.json` (git-ignored, `internal_only: true`); `pipelines/check_data.py` verifies the public file is address-free and the internal file is untracked.

## 2. Derived configuration (configs/)
| File | Content | Built by |
|---|---|---|
| `emissions_factors.csv` | factors with units, scope, T&D status, source | manual from 1.5 (verified) |
| `epc_codes.json` | EPC API code lookups | EPC API `/api/codes` |
| `retrofit_catalogue.json` (cat-v3) | 7 measures: rules, impacts, basis, sources, segments, costs | `pipelines/build_catalogue.py` |
| `score_params.json` (score-params-v1) | intensity p10/p90 from TRAIN homes | `pipelines/freeze_score_params.py` |
| `demo_homes.json` | 3 TEST-split demo homes: home_id, label, public fields, outward postcode, engine_expectations (no addresses) | `pipelines/select_demo_homes.py` (also writes the ignored `data/processed/region=york/demo_homes_internal.json`) |
| `feature_availability.json` | role of every homes_tagged column (feature_ok, label_only, identifier, metadata, deprecated, restricted_address) | `pipelines/build_feature_availability.py` |
| `value_gate.json` | sales-match audit result and value-model gate (DECISIONS D10) | `pipelines/audit_sales_matches.py` |
| `reference_docs/epc_domestic_data_dictionary.csv` | official EPC field definitions | EPC service |
| `reference_docs/ECUK_2026_End_Use_tables.xlsx` (committed) | DESNZ Energy Consumption in the UK 2026, End uses data tables (Table U3: domestic gas end-use split). Licence: Open Government Licence v3.0. Accessed 2026-10-10 | https://www.gov.uk/government/statistics/energy-consumption-in-the-uk-2026 (file: https://assets.publishing.service.gov.uk/media/6aac067444ec1aa417346c38/ECUK_2026_End_Use_tables.xlsx) |

### 2.1 Retrofit catalogue (cat-v3)
- NEED-based (validated = true): loft 3.21% (n 1,486), cavity 11.98% (n 2,191), solid wall 17.28% (n 2,411) of total gas; solar PV 12.23% (n 25,199) of grid electricity. low/high = lower/higher of headline mean and median. Segment rows (EPC rating, age, type, region) in `impact_by_segment`.
- Brief illustrative (validated = false): double glazing 8-12% and smart thermostat 5-10% of space-heat demand.
- Heat pump (validated = false): SCOP 3.0 (2.5-3.5), assumption; gas falls, electricity rises.
- Globals: boiler efficiency 0.85 (assumption); `other_gas_share` 0.0305 = cooking etc. (ECUK 2026 Table U3, UK domestic gas, mean 2021-2025; national average); `space_share_of_heat_water_gas` 0.77 and `water_share_of_heat_water_gas` 0.23 (assumptions from ECUK 0.773/0.227; cat-v2 used 0.75/0.25); `heat_pump_scop` 2.5/3.0/3.5. See DECISIONS D9, D11.
- Costs: York EPC recommendations `indicative_cost`, certificates lodged 2022+; low/mid/high = p25/median/p75 of range midpoints, plus median assessor range bounds. These are software default price ranges, not observed installation costs. Heat pump: 31 values, one text ("£5,000 - £30,000"): low confidence.

### 2.2 Score parameters (score-params-v1)
Intensity = (baseline_gas_kwh + baseline_elec_kwh) / floor_area_m2 on TRAIN homes. p10 75.749, median 137.732, p90 186.022 kWh/m²/yr; n 43,032 of 46,151 (excluded: 2,918 gas baseline unavailable, 105 zero/negative EPC energy, 42 gas boiler without mains gas, 37 no heating description, 17 implausible floor area; each home counted under its first reason). Read only from the config; never recompute.

## 3. Tagged homes (`homes_tagged.parquet`, 65,872 rows)
Adds to `homes.parquet` (unchanged):
- `prov_<field>`: observed | modelled | population_benchmark | assumption | unavailable for key fields. Baselines = population_benchmark (gas 0 for no-mains-gas homes = observed); NEED-band mappings = population_benchmark; `smart_controls` = assumption (proxy).
- `benchmark_cell_level`: coarser of the gas/electricity benchmark levels used.
- `epc_modelled_energy_kwh_m2` (kWh/m²/yr, provenance `observed`, note column `note_epc_modelled_energy_kwh_m2`): EPC modelled energy per m²; primary vs delivered not stated by the data dictionary. Identical values to the **deprecated** `epc_predicted_consumption_kwh_m2_primary`.
- Flags: `flag_gas_boiler_no_mains_gas` (56), `flag_energy_zero_or_negative` (144), `flag_no_heating_description` (55), `flag_gas_connection_unknown` (3,299: mains gas unknown **and** not gas-heated; gas-heated homes evidently have a connection), `flag_stale_epc` (21,358; `epc_age_years` > 10 at 2026-10-10).
- `data_warnings` (list of messages), `n_data_warnings`.
- `improvement_potential_status`: "unavailable" (4,415) when any blocking flag is set or baseline/area is missing or total baseline <= 0; the engine must report improvement potential as unavailable for these, never divide.

## 4. Synthetic monthly data (SYNTHETIC: annualisation demo only)
`data/processed/region=york/monthly_synthetic.parquet` (12,072 rows; 3 demo + 500 random TRAIN homes). Generated by `pipelines/make_monthly_demo.py` from annual **population benchmarks** using fixed seasonal shares (gas Jan .16 ... Dec .12; elec Jan .10 ... Dec .10), multiplicative noise N(1, 0.05), ~7% of months removed at random (841, value null). Every row `provenance = "synthetic"`. **Not measured data; not for training or evaluation of energy models.** `pipelines/annualise.py`: yearly = sum(available) / sum(pattern of available months); >6 missing -> unavailable; missing never 0.

## 5. Schema: `eval/test_predictions.csv` (defined, not yet produced)
One row per TEST-split home (and per scenario if scenarios are evaluated).

| Column | Type / unit | Available at prediction time? | Notes |
|---|---|---|---|
| property_id | string | yes | from homes_tagged |
| split | "test" | yes | |
| scenario_id | string | yes | "baseline" or retrofit package id |
| model_version | string | yes | e.g. score/catalogue/model versions |
| green_home_score | int 0-100 | output | |
| score_class | category | output | Highly efficient / Good / Moderate / Poor / Very poor |
| subscore_<component> (x7) | float 0-100 | output | plus `subscore_<component>_status` |
| baseline_gas_kwh, baseline_elec_kwh | kWh/yr | yes (population_benchmark) | |
| pred_gas_kwh, pred_elec_kwh | kWh/yr | output | modelled consumption |
| after_gas_kwh, after_elec_kwh | kWh/yr | output | post-retrofit |
| saving_gas_kwh, saving_elec_kwh, saving_net_kwh | kWh/yr | output | baseline - after; positive = reduction |
| improvement_potential_pct | % | output | null when improvement_potential_status = unavailable |
| improvement_potential_status | category | output | |
| co2e_reduction_kg | kg CO2e/yr | output | from configs/emissions_factors.csv |
| recommended_measures | list | output | ordered |
| value_uplift_pct_low/mid/high | % | output | indicative |
| prediction_status | category | output | ok / unavailable / partial |
| **Not available at prediction time (labels / leakage risk):** | | | |
| rec_* (assessor recommendations) | 0/1 | **no** | reference labels for relevance evaluation only |
| sale price, epc_rating_at_sale | GBP / A-G | **no** | value-model labels only |
| retrofit_history after the latest certificate | | **no** | |
| NEED metered readings | kWh | **no** (not linkable) | benchmark source only |
