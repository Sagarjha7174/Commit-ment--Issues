# Demo homes (TEST split)

Selected by `pipelines/select_demo_homes.py`. 'Poor' uses EPC rating E/F/G as a proxy because the Green Home Score is not built yet.

Addresses and full postcodes are **not shown**: EPC address data may only be used for energy-efficiency purposes and must not be published (see docs/DATA.md). Homes are identified by label and `home_id` (= property_id: UPRN or address hash).

## Demo home A, 1967-1975 detached house, York

`home_id`: `U100050529765`. Case `a_poor_gas_house`. EPC E used as proxy for 'Poor' class (score not built yet); gas boiler; walls and roof rated poor; partial glazing. 35 test homes matched; first by property_id.

| Field | Value |
|---|---|
| rating | E |
| sap_score | 48 |
| property_type | House |
| built_form | Detached |
| age_band | 1967-1975 |
| floor_area_m2 | 171.0 |
| walls_rating | Poor |
| walls_rating_status | observed |
| roof_rating | Very Poor |
| roof_rating_status | observed |
| glazing | partial |
| heating_type | gas_boiler |
| controls | full |
| solar_pv | False |
| mains_gas | True |
| baseline_gas_kwh | 21616.666666666664 |
| gas_status | population_benchmark |
| prov_baseline_gas_kwh | population_benchmark |
| baseline_elec_kwh | 3766.6666666666665 |
| elec_status | population_benchmark |
| prov_baseline_elec_kwh | population_benchmark |
| benchmark_cell_level | L1_fuel_type_epc_area |
| epc_age_years | 3.72 |
| improvement_potential_status | computable |
| postcode_outward | YO31 |
| data_warnings | [] |

**Engine expectations**

- expected class Poor or Very poor once the score is built (EPC E is only a proxy); fabric measures before heat pump

## Demo home B, 2003-2006 flat, York

`home_id`: `A012dcfda4e502be0`. Case `b_flat_loft_solar_infeasible`. Flat with another dwelling above (roof N/A) so loft insulation is infeasible; flats are excluded from solar PV. 803 test homes matched; first by property_id.

| Field | Value |
|---|---|
| rating | B |
| sap_score | 81 |
| property_type | Flat |
| built_form | Detached |
| age_band | 2003-2006 |
| floor_area_m2 | 30.0 |
| walls_rating | Good |
| walls_rating_status | observed |
| roof_rating | None |
| roof_rating_status | not_applicable |
| glazing | double |
| heating_type | electric |
| controls | timer |
| solar_pv | False |
| mains_gas | False |
| baseline_gas_kwh | 0.0 |
| gas_status | no_mains_gas |
| prov_baseline_gas_kwh | observed |
| baseline_elec_kwh | 2700.0 |
| elec_status | population_benchmark |
| prov_baseline_elec_kwh | population_benchmark |
| benchmark_cell_level | L1_fuel_type_epc_area |
| epc_age_years | 0.41 |
| improvement_potential_status | computable |
| postcode_outward | YO1 |
| data_warnings | [] |

**Engine expectations**

- baseline gas is 0 kWh with status no_mains_gas (observed, not missing); gas-based savings and the gas-to-heat-pump conversion do not apply; any heat-pump case must start from electric heating
- electrically heated: savings from fabric measures fall on electricity, not gas
- roof N/A (another dwelling above): loft insulation infeasible
- flat: solar PV infeasible; heat pump suitability Low (outdoor space unconfirmed)

## Demo home C, 2008 detached house, York

`home_id`: `U100050565716`. Case `c_missing_data`. No wall rating (not_applicable); data warnings: ['no usable main heating description', 'mains gas connection unknown', 'latest EPC older than 10 years']. 5 test homes lack a wall rating; most warnings first.

| Field | Value |
|---|---|
| rating | B |
| sap_score | 83 |
| property_type | House |
| built_form | Detached |
| age_band | 2008 |
| floor_area_m2 | 188.0 |
| walls_rating | None |
| walls_rating_status | not_applicable |
| roof_rating | None |
| roof_rating_status | not_applicable |
| glazing | None |
| heating_type | None |
| controls | None |
| solar_pv | None |
| mains_gas | None |
| baseline_gas_kwh | None |
| gas_status | unknown_mains_gas |
| prov_baseline_gas_kwh | unavailable |
| baseline_elec_kwh | None |
| elec_status | unavailable |
| prov_baseline_elec_kwh | unavailable |
| benchmark_cell_level | None |
| epc_age_years | 17.87 |
| improvement_potential_status | unavailable |
| postcode_outward | YO32 |
| data_warnings | ['no usable main heating description', 'mains gas connection unknown', 'latest EPC older than 10 years'] |

**Engine expectations**

- improvement potential must be reported as 'unavailable' (no division by a missing/zero baseline)
- baseline gas unavailable (status unknown_mains_gas); do not substitute 0
- baseline electricity unavailable (status unavailable); do not substitute 0
- no heating description: heating sub-score and heat-pump feasibility are unknown, not 'no heating'
- roof N/A (another dwelling above): loft insulation infeasible
- wall rating missing (status not_applicable): wall measures and the insulation sub-score must be flagged as uncertain
