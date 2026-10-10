# Labels and reference estimates

For every target we will evaluate: where it comes from, how it was built, and what agreement with it does and does not prove. Sources are detailed in `docs/DATA.md`; decisions in `docs/DECISIONS.md`.

## 1. Energy-model targets (annual gas and electricity)
- **Source:** NEED anonymised data 2026 (DESNZ), 4M and 50k samples: per-home annual gas and electricity, 2005-2024.
- **Construction:** `need_*.parquet`: mean of the 2022, 2023 and 2024 values whose validity flag is `V` (real meter readings). Estimated (`E`) and suppressed values are excluded: gas below 1,000 kWh (`L`) or above 50,000 kWh (`G`); electricity below 500 kWh (`L`) or above 25,000 kWh (`G`); `O` = missing. No gas meter -> gas status `no_gas_meter`, gas 0 (only legitimate zero). Meter present but no valid year -> `unavailable` (null). Values rounded to the nearest 100 kWh by DESNZ.
- **Units / corrections:** kWh per year. Gas is **weather-corrected** by DESNZ; electricity is **not**, and covers February-January years. Electricity is metered **import** (homes with PV import less than they use).
- **Features shared with EPC homes:** property type (6 NEED classes), age band (4), floor-area band (5), region, EPC band (A/B..F/G), main heating fuel (gas / not gas), loft and cavity insulation scheme flags, PV flag. Mappings EPC -> NEED in `data/processed/region=york/mappings/`.
- **What it does not prove:** NEED homes are anonymised and **cannot be linked to York EPC homes**. A model trained and tested on NEED shows performance on NEED homes; transfer to York EPC homes (different feature sources: EPC assessor fields vs NEED's administrative bands, EPCs up to 18 years old) is **unproven**. York homes have no meter readings, so York-level accuracy cannot be measured with current data.

## 2. Retrofit relevance labels
- **Source:** EPC recommendations (`recommendations-YYYY.csv`) on each York home's latest certificate: 231,548 rows; mapped by `improvement_id` (69 EPC types) to our 7 measures + `other` (`mappings/improvement_to_measure.csv`; text fallback for rows without an id). Wide 0/1 form `rec_*` in homes_tagged (role `label_only`).
- **Meaning:** what the accredited assessor's software suggested at the time of the certificate.
- **What it does not prove:** these are **context labels, not feasibility truth**. Recommendations depend on software version and lodgement year (heat pumps appear only 31 times; solar 47,128 times), may be outdated, and do not reflect cost, planning or occupant constraints. Agreement means "consistent with the EPC assessor", not "feasible" or "worth doing".

## 3. Feasibility labels
- **Source:** rule-based applicability in `configs/retrofit_catalogue.json` (`applicability_rules`, cat-v3), evaluated on homes_tagged fields. Missing inputs give "unknown", not "infeasible".
- **What it does not prove:** any ML feasibility model trained on these labels **agrees with the rules by construction**; high accuracy only shows it learned the rules. Real feasibility (survey, structure, planning, outdoor space) is not observed anywhere in our data.

## 4. Savings reference estimates
- **NEED measured impacts (validated = true):** Impact of measures 2026 (installation year 2023, England and Wales), matched intervention/control design. Headline medians: loft 3.21% (n 1,486), cavity wall 11.98% (n 2,191), solid wall 17.28% (n 2,411) of whole-home gas; solar PV 12.23% (n 25,199) of grid electricity. Segment rows (EPC rating, age, property type, region) in `impact_by_segment`.
- **Brief illustrative ranges (validated = false):** double glazing 8-12% and smart thermostat 5-10% of space-heating demand; heat pump SCOP 3.0 (2.5-3.5) assumption.
- **Simulator outputs:** per-fuel savings for a home or a package are **model outputs** built from the catalogue, the population-benchmark baseline and the gas end-use shares (D9). They are **not observations** for that home.
- **What it does not prove:** NEED impacts are average effects across installed homes (individual outcomes range widely: loft interquartile range -16% to +22%); they do not validate the glazing, thermostat or heat-pump figures, nor savings for any specific York home.

## 5. Value labels
- **Source:** HM Land Registry Price Paid 2025-26, York district: 4,095 standard sales; 4,000 linked to an EPC home (3,958 exact, 42 fuzzy; ambiguous matches not linked). `epc_rating_at_sale` = latest certificate lodged on or before the sale date (checked: no future certificates).
- **Match quality:** manual audit of 50 linked matches -> `configs/value_gate.json`. Currently `audit_pending`, so the value model is **not enabled** (D10). Precision from 50 rows has a wide interval.
- **What it does not prove:** price differences between rating bands are **associations**, not causal effects of retrofits (condition, location within district, size and buyer mix confound them). With ~20 months of sales, repeat sales are rare, so before/after-retrofit price changes are not observed.

## 6. Claims and evidence

| Claim | Evidence | What it does not prove |
|---|---|---|
| Energy model predicts household consumption | Held-out NEED metrics vs group-median baseline | Accuracy on York EPC homes (not linkable, no York meters) |
| Baseline energy for a York home | NEED population benchmark for its type x band x area x fuel cell | That home's actual consumption |
| Retrofit list is relevant | Overlap with EPC assessor recommendations (`rec_*`) | Feasibility, cost-effectiveness, occupant acceptance |
| Retrofit is feasible | Catalogue rules on EPC fields | Physical/planning feasibility (rules agree with themselves) |
| Loft/cavity/solid wall/solar savings | NEED Impact of measures 2023 (measured, matched control) | Savings for a specific home; figures for other measures |
| Glazing/thermostat/heat-pump savings | Brief illustrative ranges, SCOP assumption | Any measured effect (validated = false) |
| Carbon reduction | DESNZ 2026 factors x modelled kWh change | More certainty than the kWh estimate it multiplies |
| Value uplift | Land Registry prices vs EPC rating at sale (matched, audited) | Causal effect of retrofitting on price |
| Data integrity | `pipelines/check_data.py` (9 checks) | Correctness of the source registers themselves |

## 7. Limitations
- **Baselines are benchmarks, not meter readings** (D6): every York `baseline_*_kwh` is the median of similar NEED homes in Yorkshire and The Humber.
- **Stale EPCs:** 21,358 homes (32%) have a latest certificate older than 10 years (`flag_stale_epc`); features may have changed since.
- **Mislabelled EPC energy unit:** `epc_predicted_consumption_kwh_m2_primary` claimed "primary" energy without evidence; use `epc_modelled_energy_kwh_m2` (D7).
- **Demo homes:** 3 homes selected by rule from the TEST split; they illustrate behaviour and are not representative.
- **Sales:** 2025-26 only (about 20 months), one district; value labels are thin and associational.
- **End-use shares:** gas cooking share is a UK national average (ECUK); space/water split 0.77/0.23 is an assumption based on ECUK (D9, D11).
- **Costs:** EPC software default price ranges, not installation prices; heat pump cost from one text (low confidence).
- **Data oddities kept, not corrected:** e.g. demo home C is a detached house whose roof rating is N/A in its 2008 certificate.
